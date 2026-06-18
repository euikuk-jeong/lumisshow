import os
from datetime import datetime

import pytest
from PIL import Image

from backend.services.thumbnail import (
    generate_thumbnail,
    get_image_meta,
    thumb_path,
)


@pytest.fixture
def img_path(tmp_path):
    p = str(tmp_path / "test.jpg")
    Image.new("RGB", (1000, 800), color=(100, 150, 200)).save(p, "JPEG")
    return p


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    d = str(tmp_path / "data")
    monkeypatch.setenv("DATA_DIR", d)
    return d


def test_generate_thumbnail_small(data_dir, img_path):
    out = generate_thumbnail(img_path, "small")
    assert os.path.exists(out)
    with Image.open(out) as t:
        assert t.width <= 300
        assert t.height <= 200


def test_generate_thumbnail_medium(data_dir, img_path):
    out = generate_thumbnail(img_path, "medium")
    assert os.path.exists(out)
    with Image.open(out) as t:
        assert t.width <= 800
        assert t.height <= 600


def test_thumbnail_aspect_ratio_preserved(data_dir, img_path):
    """1000x800 → small(300x200): 비율 유지 → 250x200 또는 300x240 아닌 250x200"""
    out = generate_thumbnail(img_path, "small")
    with Image.open(out) as t:
        # 1000:800 = 5:4 비율. 300x200 박스 안에서 → 250x200
        assert t.width == 250
        assert t.height == 200


def test_thumbnail_cached_not_regenerated(data_dir, img_path):
    out1 = generate_thumbnail(img_path, "small")
    mtime1 = os.path.getmtime(out1)
    out2 = generate_thumbnail(img_path, "small")
    assert out1 == out2
    assert os.path.getmtime(out2) == mtime1


def test_thumbnail_output_is_jpeg(data_dir, img_path):
    out = generate_thumbnail(img_path, "small")
    with Image.open(out) as t:
        assert t.format == "JPEG"


def test_get_image_meta_dimensions(img_path):
    meta = get_image_meta(img_path)
    assert meta["width"] == 1000
    assert meta["height"] == 800


def test_get_image_meta_no_exif(img_path):
    meta = get_image_meta(img_path)
    assert meta["taken_at"] is None


def test_get_image_meta_with_exif(tmp_path):
    """EXIF DateTimeOriginal이 있으면 taken_at 파싱."""
    from PIL.Image import Exif
    img = Image.new("RGB", (100, 100))
    exif = img.getexif()
    exif[36867] = "2024:03:15 10:30:00"  # DateTimeOriginal
    p = str(tmp_path / "exif.jpg")
    img.save(p, "JPEG", exif=exif.tobytes())

    meta = get_image_meta(p)
    assert meta["taken_at"] == datetime(2024, 3, 15, 10, 30, 0)


def test_get_image_meta_invalid_file(tmp_path):
    p = str(tmp_path / "broken.jpg")
    with open(p, "wb") as f:
        f.write(b"not an image")
    meta = get_image_meta(p)
    assert set(meta.keys()) == {
        "width", "height", "taken_at", "make", "camera", "software",
        "shutter", "aperture", "iso", "focal_length", "shoot_mode",
        "flash", "metering", "exposure_mode",
    }
    assert all(v is None for v in meta.values())


def test_thumb_path_deterministic(img_path):
    """같은 파일 경로 + 같은 size → 항상 같은 thumb_path."""
    p1 = thumb_path(img_path, "small")
    p2 = thumb_path(img_path, "small")
    assert p1 == p2


def test_thumb_path_different_sizes(img_path):
    assert thumb_path(img_path, "small") != thumb_path(img_path, "medium")
