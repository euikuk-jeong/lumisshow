"""InsightFace(buffalo_l) 검출+임베딩 파이프라인.

insightface/onnxruntime은 무거운 의존성이라 lazy import — 스캔 로직 테스트 시
모델 없이도 모듈을 import할 수 있다.
"""

import json
import logging
import math
import os
import sqlite3
from dataclasses import dataclass

import numpy as np
from PIL import ExifTags, Image, ImageOps

from ai_worker import config, geocoder, matcher, tag_vocab
from ai_worker.tagger import ClipTaggingContext

_logger = logging.getLogger(__name__)

# buffalo_l 얼굴 크롭 썸네일 저장 크기
_CROP_SIZE = 160
# 초대형 원본은 검출 전 축소 (긴 변 기준) — 메모리 스파이크 방지
_MAX_ANALYZE_DIM = 2048


@dataclass
class DetectedFace:
    bbox: tuple[float, float, float, float]  # 원본 좌표계 [x1, y1, x2, y2]
    det_score: float
    embedding: np.ndarray  # float32 512


def _extract_gps(img: Image.Image) -> tuple[float, float] | None:
    """GPS EXIF(위도, 경도)를 도(decimal degree)로 변환해 반환. 없거나 파싱 실패 시 None.
    ImageOps.exif_transpose()는 반환 이미지에서 exif가 유실될 수 있어, 호출 전
    원본 이미지에서 읽어야 한다."""
    try:
        exif = img.getexif()
        if not exif:
            return None
        gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
        if not gps:
            return None
        lat, lat_ref = gps.get(2), gps.get(1)
        lon, lon_ref = gps.get(4), gps.get(3)
        if not lat or not lon or not lat_ref or not lon_ref:
            return None
        d, m, s = (float(v) for v in lat)
        latitude = d + m / 60 + s / 3600
        if lat_ref in ("S", "s"):
            latitude = -latitude
        d, m, s = (float(v) for v in lon)
        longitude = d + m / 60 + s / 3600
        if lon_ref in ("W", "w"):
            longitude = -longitude
        if not (math.isfinite(latitude) and math.isfinite(longitude)):
            # Pillow IFDRational은 EXIF 분수 필드의 분모가 0이면 예외 없이 nan을
            # 반환한다(깨진 GPS 태그) — 그대로 넘기면 geocoder의 cKDTree.query가 죽는다.
            return None
        return latitude, longitude
    except (TypeError, ValueError, ZeroDivisionError, KeyError):
        return None


class FacePipeline:
    def __init__(self) -> None:
        from insightface.app import FaceAnalysis  # lazy import

        self.app = FaceAnalysis(
            name="buffalo_l",
            root=config.model_root(),
            allowed_modules=["detection", "recognition"],
            providers=["CPUExecutionProvider"],
        )
        size = config.det_size()
        self.app.prepare(ctx_id=-1, det_size=(size, size))

    def analyze(
        self, image_path: str
    ) -> tuple[list[DetectedFace], Image.Image, tuple[float, float] | None]:
        """얼굴 목록, (크롭 저장용) 로드된 이미지, GPS 좌표(있으면)를 반환."""
        with Image.open(image_path) as img:
            gps = _extract_gps(img)  # exif_transpose가 exif를 날리기 전에 먼저 읽는다
            img = ImageOps.exif_transpose(img).convert("RGB")
            scale = 1.0
            if max(img.size) > _MAX_ANALYZE_DIM:
                scale = _MAX_ANALYZE_DIM / max(img.size)
                small = img.resize(
                    (round(img.width * scale), round(img.height * scale)),
                    Image.BILINEAR,
                )
            else:
                small = img.copy()

        bgr = np.asarray(small)[:, :, ::-1]  # insightface는 BGR 입력
        faces = []
        for f in self.app.get(bgr):
            if f.det_score < config.min_det_score():
                continue
            x1, y1, x2, y2 = (float(v) / scale for v in f.bbox)
            faces.append(
                DetectedFace(
                    bbox=(x1, y1, x2, y2),
                    det_score=float(f.det_score),
                    embedding=np.asarray(f.normed_embedding, dtype=np.float32),
                )
            )
        return faces, img, gps


def _load_image(abs_path: str) -> tuple[Image.Image, tuple[float, float] | None]:
    """얼굴 검출 없이 회전 보정된 이미지와 GPS만 읽는다 — 얼굴 인식 카테고리가
    꺼졌을 때(analyze_and_store)와 tag-backfill(backfill_photo)에서 공용으로 쓴다."""
    with Image.open(abs_path) as raw:
        gps = _extract_gps(raw)
        img = ImageOps.exif_transpose(raw).convert("RGB")
    return img, gps


def save_face_crop(img: Image.Image, face: DetectedFace, face_id: int) -> None:
    """얼굴 영역을 여유 마진(25%) 포함해 크롭 → DATA_DIR/faces/{face_id}.jpg"""
    x1, y1, x2, y2 = face.bbox
    margin = 0.25 * max(x2 - x1, y2 - y1)
    box = (
        max(0, round(x1 - margin)),
        max(0, round(y1 - margin)),
        min(img.width, round(x2 + margin)),
        min(img.height, round(y2 + margin)),
    )
    crop = img.crop(box)
    crop.thumbnail((_CROP_SIZE, _CROP_SIZE), Image.LANCZOS)
    os.makedirs(config.faces_dir(), exist_ok=True)
    crop.save(os.path.join(config.faces_dir(), f"{face_id}.jpg"), "JPEG", quality=90)


def _update_location(
    conn: sqlite3.Connection, rel_path: str, gps: tuple[float, float] | None
) -> bool:
    """GPS가 있으면 역지오코딩 후 photo_locations를 갱신, 없으면(또는 조회 실패) 기존
    행을 지운다 — 재분석 시 이전엔 있던 GPS가 사라진 경우도 반영해야 하기 때문.
    photo_tags(source='location') 동기화는 항상 geocoder.sync_location_tag가 맡는다.
    역지오코딩 자체의 실패는 얼굴 분석 성공 여부에 영향을 주지 않는다(best-effort).
    위치가 실제로 기록됐는지(city/country 확보) 여부를 반환 — 스캔 결과 집계용."""
    if gps is not None:
        try:
            city, country = geocoder.reverse_geocode(*gps)
        except Exception:
            _logger.exception("%s 역지오코딩 실패", rel_path)
            city = country = None
    else:
        city = country = None

    if city or country:
        conn.execute(
            """INSERT INTO photo_locations (photo_path, city, country, source)
               VALUES (?, ?, ?, 'exif_gps')
               ON CONFLICT(photo_path) DO UPDATE SET
                 city=excluded.city, country=excluded.country, source='exif_gps',
                 tagged_at=CURRENT_TIMESTAMP""",
            (rel_path, city, country),
        )
    else:
        conn.execute("DELETE FROM photo_locations WHERE photo_path = ?", (rel_path,))
    geocoder.sync_location_tag(conn, rel_path)
    return bool(city or country)


def _score_and_store_ai_tags(
    conn: sqlite3.Connection,
    rel_path: str,
    embed: np.ndarray,
    clip_ctx: ClipTaggingContext,
) -> None:
    """주어진(이미 계산된) 임베딩으로 현재 어휘/threshold 기준 photo_tags(source='ai')를
    갱신한다(기존 'ai' 태그 삭제 후 재삽입) — 이미지 재인코딩은 하지 않는다."""
    conn.execute("DELETE FROM photo_tags WHERE photo_path = ? AND source = 'ai'", (rel_path,))
    sims = clip_ctx.text_embeds @ embed
    for i, sim in enumerate(sims):
        if sim >= clip_ctx.threshold:
            conn.execute(
                """INSERT INTO photo_tags (photo_path, tag, source, confidence)
                   VALUES (?, ?, 'ai', ?)
                   ON CONFLICT(photo_path, tag, source) DO NOTHING""",
                (rel_path, tag_vocab.TAG_VOCAB[i]["label"], float(sim)),
            )


def _update_ai_tags(
    conn: sqlite3.Connection,
    rel_path: str,
    img: Image.Image,
    clip_ctx: ClipTaggingContext | None,
) -> bool:
    """이미지를 새로 인코딩해 photo_embeddings에 저장하고 photo_tags(source='ai')를
    갱신한다(scan 경로 — 사진 콘텐츠가 바뀌었을 수 있는 재분석 상황이라 캐시를
    신뢰할 수 없어 매번 새로 인코딩). 어휘/threshold만 바뀌고 이미지는 그대로인
    경우의 재채점은 `rescore_ai_tags_from_cache`(tag-backfill 전용, 재인코딩 없음)를 쓴다.

    clip_ctx가 없거나(CLIP 모델 로딩 실패) 임베딩 자체가 실패하면 기존 'ai' 태그를
    그대로 둔 채 아무 것도 하지 않는다 — best-effort지만, Kiwi/GPS와 달리 CLIP은
    실패 시 다음 스캔에서도 자동으로 다시 채워지지 않는(coverage 방식이 아닌)
    유일한 트랙이라 지우기만 하고 못 채우면 영구 유실이 된다. 조금 낡은 태그가
    남는 쪽이 안전하다. 임베딩을 새로 반영했는지 여부를 반환 — 스캔 결과 집계용."""
    if clip_ctx is None:
        return False
    try:
        embed = clip_ctx.tagger.embed_image(img)
    except Exception:
        _logger.exception("%s CLIP 임베딩 실패", rel_path)
        return False

    conn.execute(
        """INSERT INTO photo_embeddings (photo_path, embedding) VALUES (?, ?)
           ON CONFLICT(photo_path) DO UPDATE SET
             embedding=excluded.embedding, updated_at=CURRENT_TIMESTAMP""",
        (rel_path, matcher.embedding_to_blob(embed)),
    )
    _score_and_store_ai_tags(conn, rel_path, embed, clip_ctx)
    return True


def rescore_ai_tags_from_cache(
    conn: sqlite3.Connection, rel_path: str, clip_ctx: ClipTaggingContext | None
) -> bool:
    """photo_embeddings에 이미 저장된 벡터를 그대로 재사용해 현재 어휘/threshold로만
    재채점한다(tag-backfill 전용) — 이미지를 다시 열거나 재인코딩하지 않는다. 이게
    photo_embeddings를 캐시해두는 핵심 이유: 어휘 확장·threshold 조정이 전체 재인코딩
    (사진 수만 장 기준 수십 분~수 시간) 없이 벡터 비교(수십 밀리초)만으로 끝난다.
    캐시된 임베딩이 없으면(아직 한 번도 인코딩 안 된 사진) False를 반환하고 아무 것도
    하지 않는다 — 그 경우는 `_update_ai_tags`로 새로 인코딩해야 한다.

    `_update_ai_tags`(scan 경로)와 달리 여기서는 재채점 결과 'ai' 태그가 0개가 되어도
    기존 태그를 그대로 삭제한다 — admin이 threshold를 올리는 등 명시적으로 재계산을
    요청한 결과이므로 "낡은 태그가 남는 쪽이 안전하다"는 Phase 3의 best-effort 원칙이
    적용되지 않는다. embed_image() 실패로 태그를 잃는 실패 시나리오 자체가 없다
    (임베딩은 이미 캐시돼 있으므로)."""
    if clip_ctx is None:
        return False
    row = conn.execute(
        "SELECT embedding FROM photo_embeddings WHERE photo_path = ?", (rel_path,)
    ).fetchone()
    if row is None:
        return False
    embed = matcher.blob_to_embedding(row["embedding"])
    _score_and_store_ai_tags(conn, rel_path, embed, clip_ctx)
    return True


def backfill_photo(
    conn: sqlite3.Connection,
    rel_path: str,
    abs_path: str,
    clip_ctx: ClipTaggingContext | None,
    need_embedding: bool,
    need_location: bool,
) -> tuple[bool, bool]:
    """tag-backfill 전용: 얼굴 재분석 없이 CLIP 임베딩/위치만 소급 반영한다(파일을
    1번만 연다). (임베딩을 새로 채웠는지, 위치를 새로 채웠는지)를 반환 — 파일을
    열 수 없으면 예외를 그대로 던진다(호출부인 main.run_tag_backfill이 건너뛰고
    계속 진행)."""
    img, gps = _load_image(abs_path)

    embedded = False
    if need_embedding:
        _update_ai_tags(conn, rel_path, img, clip_ctx)
        embedded = True

    located = False
    if need_location and gps is not None:
        _update_location(conn, rel_path, gps)
        located = True

    return embedded, located


def analyze_and_store(
    pipeline: FacePipeline | None,
    conn: sqlite3.Connection,
    rel_path: str,
    mtime: float,
    enrollment: dict[int, np.ndarray],
    threshold: float,
    clip_ctx: ClipTaggingContext | None = None,
    location_enabled: bool = True,
) -> tuple[int, bool, bool, bool]:
    """사진 1장 분석 → faces/face_matches/photos_analyzed/photo_locations/
    photo_embeddings 기록 (1장 = 1커밋, resumable).

    재분석(mtime 변경) 시 기존 얼굴 행은 삭제 후 새로 기록.
    (이번 스캔에서 검출한 얼굴 수, 성공 여부, 위치 반영 여부, AI 태그 반영 여부)를
    반환 — 호출부(main.run_scan)가 이 값을 합산해 "이번 스캔에서 몇 개 검출했는지"
    로그·Discord 알림에 쓰므로, 얼굴 인식이 꺼져 기존 얼굴을 그대로 뒀을 뿐인
    경우까지 여기 섞이면 안 된다(재스캔마다 진짜 검출량과 무관하게 숫자가 널뛴다).
    실패 시 status='error'로 기록하고 (0, False, False, False) 반환.

    카테고리 on/off(Admin 설정)는 "끄면 새로 생성하지 않지만 기존 데이터는
    지우지 않는다" 원칙을 따른다:
    - `pipeline`이 None이면 얼굴 인식이 꺼진 상태 — 얼굴 검출을 건너뛰고
      `faces`/`face_matches`를 건드리지 않는다(DELETE도 하지 않음). 반환값의
      얼굴 수는 항상 0(이번 스캔에서 새로 검출한 게 없다는 뜻)이고,
      `photos_analyzed.face_count`는 이와 별개로 현재 `faces`에 남아 있는
      행 수를 그대로 기록한다(둘의 의미가 다르다).
    - `location_enabled`가 False면 `_update_location` 호출 자체를 생략해
      기존 `photo_locations`를 보존한다.
    - `clip_ctx`가 None이면(사물 태깅이 꺼졌거나 CLIP 로딩 실패) `_update_ai_tags`가
      기존 태그를 그대로 둔 채 아무 것도 하지 않는다(이미 그렇게 동작함).
    """
    abs_path = os.path.join(config.photo_root(), rel_path)
    try:
        if pipeline is not None:
            faces, img, gps = pipeline.analyze(abs_path)
        else:
            faces = None
            img, gps = _load_image(abs_path)
    except Exception:
        _logger.exception("%s 분석 실패", rel_path)
        conn.execute(
            """INSERT INTO photos_analyzed (path, mtime, face_count, status)
               VALUES (?, ?, 0, 'error')
               ON CONFLICT(path) DO UPDATE SET
                 mtime=excluded.mtime, face_count=0, status='error',
                 analyzed_at=CURRENT_TIMESTAMP""",
            (rel_path, mtime),
        )
        conn.commit()
        return 0, False, False, False

    if faces is not None:
        conn.execute("DELETE FROM faces WHERE photo_path = ?", (rel_path,))
        for face in faces:
            cur = conn.execute(
                "INSERT INTO faces (photo_path, bbox, det_score, embedding) VALUES (?, ?, ?, ?)",
                (
                    rel_path,
                    json.dumps([round(v, 1) for v in face.bbox]),
                    face.det_score,
                    matcher.embedding_to_blob(face.embedding),
                ),
            )
            face_id = cur.lastrowid
            save_face_crop(img, face, face_id)
            result = matcher.match_one(face.embedding, enrollment, threshold)
            if result is not None:
                conn.execute(
                    "INSERT INTO face_matches (face_id, person_id, score) VALUES (?, ?, ?)",
                    (face_id, result[0], result[1]),
                )
        stored_face_count = len(faces)
        detected_face_count = stored_face_count
    else:
        # 얼굴 인식이 꺼진 상태 — photos_analyzed.face_count는 현재 남아있는 행 수를
        # 그대로 기록하되(조회용 통계), 반환값(이번 스캔에서 "새로 검출"한 수)은
        # 항상 0이어야 한다. 둘을 같은 값으로 쓰면 재분석 때마다 검출량과 무관하게
        # summary["faces"]/로그/Discord 알림 숫자가 기존 얼굴 수만큼 부풀어 오른다.
        stored_face_count = conn.execute(
            "SELECT COUNT(*) FROM faces WHERE photo_path = ?", (rel_path,)
        ).fetchone()[0]
        detected_face_count = 0

    located = _update_location(conn, rel_path, gps) if location_enabled else False
    tagged = _update_ai_tags(conn, rel_path, img, clip_ctx)

    conn.execute(
        """INSERT INTO photos_analyzed (path, mtime, face_count, status)
           VALUES (?, ?, ?, 'done')
           ON CONFLICT(path) DO UPDATE SET
             mtime=excluded.mtime, face_count=excluded.face_count, status='done',
             analyzed_at=CURRENT_TIMESTAMP""",
        (rel_path, mtime, stored_face_count),
    )
    conn.commit()
    return detected_face_count, True, located, tagged
