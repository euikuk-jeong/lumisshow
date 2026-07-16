import hashlib
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps

SIZES: dict[str, tuple[int, int]] = {
    "small": (300, 200),
    "medium": (800, 600),
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".tiff", ".bmp"}

_EXIF_DATETIME_ORIGINAL = 36867
_EXIF_DATETIME = 306


def _thumb_dir() -> str:
    return os.path.join(os.getenv("DATA_DIR", "./testdata/data"), "thumbnails")


def thumb_filename(file_path: str, size: str) -> str:
    md5 = hashlib.md5(file_path.encode()).hexdigest()
    return f"{md5}_{size}.jpg"


def thumb_path(file_path: str, size: str) -> str:
    return os.path.join(_thumb_dir(), thumb_filename(file_path, size))


_thumb_locks: dict[str, threading.Lock] = {}
_thumb_locks_mutex = threading.Lock()

# 동시 썸네일 생성(원본 디코딩) 개수 제한 — 그리드 첫 로딩 시 수십 개 요청이
# 동시에 executor 스레드로 들어와도 대형 원본 디코딩이 한꺼번에 몰려
# 메모리 스파이크가 나지 않도록 제한. 락 자체(파일별 중복 생성 방지)와는 별개.
_THUMB_MAX_CONCURRENCY = int(os.getenv("THUMB_MAX_CONCURRENCY", "4"))
_thumb_semaphore = threading.Semaphore(_THUMB_MAX_CONCURRENCY)


def _get_thumb_lock(out_path: str) -> threading.Lock:
    with _thumb_locks_mutex:
        if out_path not in _thumb_locks:
            _thumb_locks[out_path] = threading.Lock()
        return _thumb_locks[out_path]


def generate_thumbnail(file_path: str, size: str) -> str:
    """썸네일 생성 (이미 존재하면 재사용). 생성된 썸네일 절대 경로 반환."""
    out_path = thumb_path(file_path, size)
    if os.path.exists(out_path):
        return out_path

    lock = _get_thumb_lock(out_path)
    try:
        with lock:
            if os.path.exists(out_path):
                return out_path
            os.makedirs(_thumb_dir(), exist_ok=True)
            max_w, max_h = SIZES[size]
            with _thumb_semaphore, Image.open(file_path) as img:
                # JPEG draft: 목표 크기보다 큰 원본을 요청 크기에 가까운 스케일(1/2, 1/4...)로
                # 디코딩해 풀해상도 디코딩 대비 속도·메모리를 크게 절감 (JPEG 외 포맷은 no-op)
                img.draft("RGB", (max_w * 2, max_h * 2))
                img = ImageOps.exif_transpose(img)
                img.thumbnail((max_w, max_h), Image.LANCZOS)
                img.convert("RGB").save(out_path, "JPEG", quality=85, optimize=True)
    finally:
        # 생성 완료 후 dict에서 제거 — 그대로 두면 앨범 내 사진 경로 수만큼 무한 증가.
        # 같은 경로로 이미 대기 중인 스레드는 위에서 얻은 lock 참조를 그대로 쓰므로 안전.
        with _thumb_locks_mutex:
            if _thumb_locks.get(out_path) is lock:
                del _thumb_locks[out_path]

    return out_path


# ── EXIF tag IDs ──────────────────────────────────────────────────────────────

_EXIF_ORIENTATION    = 274
_ROTATE_SWAP_ORIENTATIONS = {5, 6, 7, 8}

# Main IFD (IFD0)
_EXIF_MAKE           = 271
_EXIF_MODEL          = 272
_EXIF_SOFTWARE       = 305

# Exif sub-IFD (tag 34665)
_EXIF_SUB_IFD        = 0x8769
_EXIF_EXPOSURE_TIME  = 33434
_EXIF_F_NUMBER       = 33437
_EXIF_EXPOSURE_PROG  = 34850
_EXIF_ISO            = 34855
_EXIF_METERING_MODE  = 37383
_EXIF_FLASH          = 37385
_EXIF_FOCAL_LENGTH   = 37386
_EXIF_EXPOSURE_MODE  = 41985

_EXPOSURE_PROGRAM = {
    0: "Not defined", 1: "Manual", 2: "Program AE",
    3: "Aperture priority", 4: "Shutter priority",
    5: "Creative", 6: "Action", 7: "Portrait", 8: "Landscape",
}
_METERING_MODE = {
    0: "Unknown", 1: "Average", 2: "Center-weighted",
    3: "Spot", 4: "Multi-spot", 5: "Multi-segment", 6: "Partial",
}
_EXPOSURE_MODE = {0: "Auto", 1: "Manual", 2: "Auto bracket"}

_EMPTY_META: dict = {
    "width": None, "height": None, "taken_at": None,
    "make": None, "camera": None, "software": None,
    "shutter": None, "aperture": None, "iso": None, "focal_length": None,
    "shoot_mode": None, "flash": None, "metering": None, "exposure_mode": None,
}


def _to_float(val) -> Optional[float]:
    try:
        v = float(val)
        import math
        return None if math.isnan(v) or math.isinf(v) else v
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def get_image_meta(file_path: str) -> dict:
    """EXIF에서 메타데이터 추출. 실패 시 None 반환."""
    try:
        with Image.open(file_path) as img:
            width, height = img.size
            exif = img.getexif()
            if exif.get(_EXIF_ORIENTATION) in _ROTATE_SWAP_ORIENTATIONS:
                width, height = height, width

            # 카메라 설정 태그는 Exif sub-IFD에 있으므로 별도 접근
            sub = exif.get_ifd(_EXIF_SUB_IFD)

            def get(tag: int):
                v = exif.get(tag)
                return v if v is not None else sub.get(tag)

            # 촬영일
            raw_dt: Optional[str] = get(_EXIF_DATETIME_ORIGINAL) or get(_EXIF_DATETIME)
            taken_at: Optional[datetime] = None
            if raw_dt:
                try:
                    taken_at = datetime.strptime(str(raw_dt), "%Y:%m:%d %H:%M:%S")
                except ValueError:
                    pass
            if taken_at is None:
                # EXIF 촬영일 없으면 파일 mtime으로 대체 (NAS는 진짜 생성시각 못 얻음, mtime은 복사 후에도 대개 보존됨)
                try:
                    taken_at = datetime.fromtimestamp(os.path.getmtime(file_path))
                except OSError:
                    pass

            # 제작사 / 모델
            make: Optional[str] = str(exif.get(_EXIF_MAKE, "") or "").strip() or None
            model: Optional[str] = str(exif.get(_EXIF_MODEL, "") or "").strip() or None
            camera: Optional[str] = model  # 모델명만 표시

            # 소프트웨어
            software: Optional[str] = str(exif.get(_EXIF_SOFTWARE, "") or "").replace("\x00", "").strip() or None

            # 노출 시간 (셔터 스피드)
            shutter: Optional[str] = None
            val = _to_float(get(_EXIF_EXPOSURE_TIME))
            if val and val > 0:
                shutter = f"1/{round(1/val)} s" if val < 1 else f"{val:.1f} s"

            # 조리개
            f_num = _to_float(get(_EXIF_F_NUMBER))
            aperture: Optional[str] = f"f/{f_num:.1f}" if f_num else None

            # ISO
            iso_raw = get(_EXIF_ISO)
            iso: Optional[int] = int(iso_raw) if iso_raw is not None else None

            # 초점 거리
            fl = _to_float(get(_EXIF_FOCAL_LENGTH))
            focal_length: Optional[str] = f"{fl:.0f} mm" if fl else None

            # 촬영 모드 (ExposureProgram)
            ep = get(_EXIF_EXPOSURE_PROG)
            shoot_mode: Optional[str] = _EXPOSURE_PROGRAM.get(int(ep)) if ep is not None else None

            # 플래시
            flash_raw = get(_EXIF_FLASH)
            flash: Optional[str] = None
            if flash_raw is not None:
                flash = "Fired" if (int(flash_raw) & 0x1) else "No flash"

            # 측광 방식
            mm = get(_EXIF_METERING_MODE)
            metering: Optional[str] = _METERING_MODE.get(int(mm)) if mm is not None else None

            # 노출 방식
            em = get(_EXIF_EXPOSURE_MODE)
            exposure_mode: Optional[str] = _EXPOSURE_MODE.get(int(em)) if em is not None else None

            return {
                "width": width, "height": height, "taken_at": taken_at,
                "make": make, "camera": camera, "software": software,
                "shutter": shutter, "aperture": aperture, "iso": iso,
                "focal_length": focal_length, "shoot_mode": shoot_mode,
                "flash": flash, "metering": metering, "exposure_mode": exposure_mode,
            }
    except Exception:
        return dict(_EMPTY_META)
