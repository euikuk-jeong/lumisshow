import hashlib
import os
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


def generate_thumbnail(file_path: str, size: str) -> str:
    """썸네일 생성 (이미 존재하면 재사용). 생성된 썸네일 절대 경로 반환."""
    out_path = thumb_path(file_path, size)
    if os.path.exists(out_path):
        return out_path

    os.makedirs(_thumb_dir(), exist_ok=True)
    max_w, max_h = SIZES[size]

    with Image.open(file_path) as img:
        img = ImageOps.exif_transpose(img)
        img.thumbnail((max_w, max_h), Image.LANCZOS)
        img.convert("RGB").save(out_path, "JPEG", quality=85, optimize=True)

    return out_path


_EXIF_ORIENTATION = 274
_ROTATE_SWAP_ORIENTATIONS = {5, 6, 7, 8}


def get_image_meta(file_path: str) -> dict:
    """EXIF에서 촬영일, 해상도 추출. 실패 시 None 반환."""
    try:
        with Image.open(file_path) as img:
            width, height = img.size
            exif = img.getexif()
            if exif.get(_EXIF_ORIENTATION) in _ROTATE_SWAP_ORIENTATIONS:
                width, height = height, width
            raw_dt: Optional[str] = exif.get(_EXIF_DATETIME_ORIGINAL) or exif.get(_EXIF_DATETIME)
            taken_at: Optional[datetime] = None
            if raw_dt:
                try:
                    taken_at = datetime.strptime(raw_dt, "%Y:%m:%d %H:%M:%S")
                except ValueError:
                    pass
            return {"width": width, "height": height, "taken_at": taken_at}
    except Exception:
        return {"width": None, "height": None, "taken_at": None}
