"""InsightFace(buffalo_l) 검출+임베딩 파이프라인.

insightface/onnxruntime은 무거운 의존성이라 lazy import — 스캔 로직 테스트 시
모델 없이도 모듈을 import할 수 있다.
"""

import json
import os
import sqlite3
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps

from ai_worker import config, matcher

# buffalo_l 얼굴 크롭 썸네일 저장 크기
_CROP_SIZE = 160
# 초대형 원본은 검출 전 축소 (긴 변 기준) — 메모리 스파이크 방지
_MAX_ANALYZE_DIM = 2048


@dataclass
class DetectedFace:
    bbox: tuple[float, float, float, float]  # 원본 좌표계 [x1, y1, x2, y2]
    det_score: float
    embedding: np.ndarray  # float32 512


class FacePipeline:
    def __init__(self) -> None:
        from insightface.app import FaceAnalysis  # lazy import

        self.app = FaceAnalysis(
            name="buffalo_l",
            allowed_modules=["detection", "recognition"],
            providers=["CPUExecutionProvider"],
        )
        size = config.det_size()
        self.app.prepare(ctx_id=-1, det_size=(size, size))

    def analyze(self, image_path: str) -> tuple[list[DetectedFace], Image.Image]:
        """얼굴 목록과 (크롭 저장용) 로드된 이미지를 반환."""
        with Image.open(image_path) as img:
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
        return faces, img


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


def analyze_and_store(
    pipeline: FacePipeline,
    conn: sqlite3.Connection,
    rel_path: str,
    mtime: float,
    enrollment: dict[int, np.ndarray],
    threshold: float,
) -> int:
    """사진 1장 분석 → faces/face_matches/photos_analyzed 기록 (1장 = 1커밋, resumable).

    재분석(mtime 변경) 시 기존 얼굴 행은 삭제 후 새로 기록.
    검출된 얼굴 수를 반환, 실패 시 status='error'로 기록하고 0 반환.
    """
    abs_path = os.path.join(config.photo_root(), rel_path)
    try:
        faces, img = pipeline.analyze(abs_path)
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
        return 0

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

    conn.execute(
        """INSERT INTO photos_analyzed (path, mtime, face_count, status)
           VALUES (?, ?, ?, 'done')
           ON CONFLICT(path) DO UPDATE SET
             mtime=excluded.mtime, face_count=excluded.face_count, status='done',
             analyzed_at=CURRENT_TIMESTAMP""",
        (rel_path, mtime, len(faces)),
    )
    conn.commit()
    return len(faces)
