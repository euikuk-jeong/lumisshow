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


def tag_threshold() -> float:
    """CLIP zero-shot 태그 부여 임계값(코사인 유사도). 정식 eval은 생략하고
    (doc/tagging_requirement.md 결정) 실사진 15장 정성 검증(2026-08-02, 82개 어휘
    기준 평균 4.4개/사진 부여, 누락 0건)으로 잡은 초기값. `tagger.tag_threshold_setting`을
    통해 ai_settings(Admin 설정)가 있으면 이 값보다 우선한다."""
    return float(os.getenv("AI_TAG_THRESHOLD", "0.24"))


def model_root() -> str:
    """InsightFace 모델 가중치 저장 경로. DATA_DIR 볼륨에 두어 컨테이너
    재시작 시 재다운로드를 방지한다 (라이선스상 이미지에 포함하지 않음)."""
    return os.getenv("AI_MODEL_ROOT", os.path.join(data_dir(), "models"))


def scan_hour() -> int:
    """데몬 모드 야간 자동 스캔 시각 (0~23시, 로컬 TZ 기준)."""
    return int(os.getenv("AI_SCAN_HOUR", "2"))


def poll_interval() -> int:
    """데몬 모드 jobs 큐 폴링 간격 (초)."""
    return int(os.getenv("AI_POLL_INTERVAL", "30"))


def discord_webhook_url() -> str:
    """스캔/재매칭 완료 알림용 Discord webhook URL. 미설정이면 알림 스킵."""
    return os.getenv("AI_DISCORD_WEBHOOK_URL", "")


def base_url() -> str:
    """LumisShow 접속 URL. Discord 알림에 Admin People 페이지 링크를 붙이는 데 사용
    (backend의 admin_links.py와 동일 기본값/규약 공유)."""
    return os.getenv("BASE_URL", "http://localhost:8080").rstrip("/")
