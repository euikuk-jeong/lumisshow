"""InsightFace(buffalo_l) 검출+임베딩 파이프라인.

insightface/onnxruntime은 무거운 의존성이라 lazy import — 스캔 로직 테스트 시
모델 없이도 모듈을 import할 수 있다.
"""

import json
import logging
import os
import sqlite3
from dataclasses import dataclass

import numpy as np
from PIL import ExifTags, Image, ImageOps

from ai_worker import config, geocoder, matcher

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
) -> None:
    """GPS가 있으면 역지오코딩 후 photo_locations를 갱신, 없으면(또는 조회 실패) 기존
    행을 지운다 — 재분석 시 이전엔 있던 GPS가 사라진 경우도 반영해야 하기 때문.
    photo_tags(source='location') 동기화는 항상 geocoder.sync_location_tag가 맡는다.
    역지오코딩 자체의 실패는 얼굴 분석 성공 여부에 영향을 주지 않는다(best-effort)."""
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


def analyze_and_store(
    pipeline: FacePipeline,
    conn: sqlite3.Connection,
    rel_path: str,
    mtime: float,
    enrollment: dict[int, np.ndarray],
    threshold: float,
) -> tuple[int, bool]:
    """사진 1장 분석 → faces/face_matches/photos_analyzed/photo_locations 기록
    (1장 = 1커밋, resumable).

    재분석(mtime 변경) 시 기존 얼굴 행은 삭제 후 새로 기록.
    (검출된 얼굴 수, 성공 여부)를 반환. 실패 시 status='error'로 기록하고 (0, False) 반환.
    """
    abs_path = os.path.join(config.photo_root(), rel_path)
    try:
        faces, img, gps = pipeline.analyze(abs_path)
    except Exception:
        conn.execute(
            """INSERT INTO photos_analyzed (path, mtime, face_count, status)
               VALUES (?, ?, 0, 'error')
               ON CONFLICT(path) DO UPDATE SET
                 mtime=excluded.mtime, face_count=0, status='error',
                 analyzed_at=CURRENT_TIMESTAMP""",
            (rel_path, mtime),
        )
        conn.commit()
        return 0, False

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

    _update_location(conn, rel_path, gps)

    conn.execute(
        """INSERT INTO photos_analyzed (path, mtime, face_count, status)
           VALUES (?, ?, ?, 'done')
           ON CONFLICT(path) DO UPDATE SET
             mtime=excluded.mtime, face_count=excluded.face_count, status='done',
             analyzed_at=CURRENT_TIMESTAMP""",
        (rel_path, mtime, len(faces)),
    )
    conn.commit()
    return len(faces), True
