import os
import threading
import time
from datetime import datetime

import pytest
from PIL import Image

from backend.services import thumbnail as thumbnail_module
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


def test_get_image_meta_no_exif_falls_back_to_mtime(img_path):
    """EXIF 촬영일 없으면 파일 mtime으로 taken_at 대체."""
    expected = datetime.fromtimestamp(os.path.getmtime(img_path))
    meta = get_image_meta(img_path)
    assert meta["taken_at"] == expected


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


# ── JPEG draft + 동시 생성 제한 ────────────────────────────────────────────────

def test_thumbnail_large_image_draft_preserves_aspect(data_dir, tmp_path):
    """draft로 축소 디코딩되는 대형 원본도 최종 썸네일 비율이 유지돼야 한다."""
    p = str(tmp_path / "large.jpg")
    Image.new("RGB", (4000, 3000), color=(50, 60, 70)).save(p, "JPEG")
    out = generate_thumbnail(p, "small")
    with Image.open(out) as t:
        assert t.width <= 300
        assert t.height <= 200
        assert abs(t.width / t.height - 4000 / 3000) < 0.05


def test_thumbnail_generation_respects_concurrency_limit(data_dir, monkeypatch, tmp_path):
    """동시 생성 요청이 세마포어 한도를 넘지 않아야 한다."""
    monkeypatch.setattr(thumbnail_module, "_thumb_semaphore", threading.Semaphore(2))

    current = 0
    peak = 0
    counter_lock = threading.Lock()
    orig_open = thumbnail_module.Image.open

    def slow_open(path, *a, **kw):
        nonlocal current, peak
        with counter_lock:
            current += 1
            peak = max(peak, current)
        img = orig_open(path, *a, **kw)
        time.sleep(0.05)
        with counter_lock:
            current -= 1
        return img

    monkeypatch.setattr(thumbnail_module.Image, "open", slow_open)

    paths = []
    for i in range(6):
        p = str(tmp_path / f"img{i}.jpg")
        Image.new("RGB", (200, 200), color=(i * 10, 100, 100)).save(p, "JPEG")
        paths.append(p)

    threads = [threading.Thread(target=generate_thumbnail, args=(p, "small")) for p in paths]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert peak <= 2


def test_thumb_locks_cleaned_up_after_generation(data_dir, tmp_path):
    """생성 완료 후 _thumb_locks에 경로별 락이 남아있으면 안 됨 (무한 증가 방지)."""
    for i in range(5):
        p = str(tmp_path / f"cleanup{i}.jpg")
        Image.new("RGB", (200, 200), color=(i * 10, 100, 100)).save(p, "JPEG")
        generate_thumbnail(p, "small")

    assert thumbnail_module._thumb_locks == {}


def test_thumb_locks_cleaned_up_under_concurrency(data_dir, tmp_path):
    """동시 요청 후에도 _thumb_locks가 비어 있어야 함."""
    paths = []
    for i in range(6):
        p = str(tmp_path / f"conc{i}.jpg")
        Image.new("RGB", (200, 200), color=(i * 10, 100, 100)).save(p, "JPEG")
        paths.append(p)

    threads = [threading.Thread(target=generate_thumbnail, args=(p, "small")) for p in paths]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert thumbnail_module._thumb_locks == {}
