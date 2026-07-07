import os

# LumisShow backend/services/thumbnail.py의 IMAGE_EXTENSIONS와 동일하게 유지할 것
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".tiff", ".bmp"}


def photo_root() -> str:
    return os.path.realpath(os.getenv("PHOTO_ROOT", "./testdata/photos"))


def data_dir() -> str:
    return os.getenv("DATA_DIR", "./testdata/data")


def ai_db_path() -> str:
    return os.path.join(data_dir(), "db", "ai.db")


def faces_dir() -> str:
    return os.path.join(data_dir(), "faces")


def match_threshold() -> float:
    """cosine similarity 매칭 임계값. eval.py로 튜닝한 값을 환경변수로 지정."""
    return float(os.getenv("AI_MATCH_THRESHOLD", "0.45"))


def det_size() -> int:
    """SCRFD 검출 입력 크기 (정사각). NAS RAM 부족 시 480 등으로 축소."""
    return int(os.getenv("AI_DET_SIZE", "640"))


def min_det_score() -> float:
    """이 값 미만의 검출 신뢰도 얼굴은 저장하지 않음 (배경 오검출 컷)."""
    return float(os.getenv("AI_MIN_DET_SCORE", "0.5"))
