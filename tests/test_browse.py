import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image


def _make_jpg(path):
    Image.new("RGB", (10, 10)).save(str(path), "JPEG")


def _make_jpg_with_exif(path, taken_at_str: str):
    """DateTime(IFD0/306) EXIF가 포함된 JPEG 생성."""
    img = Image.new("RGB", (100, 100))
    exif = img.getexif()
    exif[306] = taken_at_str  # DateTime tag (IFD0)
    img.save(str(path), "JPEG", exif=exif.tobytes())


@pytest.fixture
def photo_root(tmp_path):
    root = tmp_path / "photos"
    root.mkdir()
    sub = root / "sub"
    sub.mkdir()

    for i in range(3):
        Image.new("RGB", (100, 100), color=(i * 50, 100, 150)).save(
            str(root / f"photo{i}.jpg"), "JPEG"
        )
    Image.new("RGB", (100, 100)).save(str(sub / "nested.jpg"), "JPEG")
    (root / "not_an_image.txt").write_text("skip me")
    return root


@pytest_asyncio.fixture
async def auth_client(tmp_path, monkeypatch, photo_root):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PHOTO_ROOT", str(photo_root))
    monkeypatch.setenv("ADMIN_PASSWORD", "testpass")
    monkeypatch.setenv("JWT_SECRET", "testsecret")

    from backend.models.database import init_db
    await init_db()

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"password": "testpass"})
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        yield c


# ── browse ────────────────────────────────────────────────────────────────────

async def test_browse_root_folders_and_photos(auth_client):
    r = await auth_client.get("/api/admin/browse")
    assert r.status_code == 200
    data = r.json()
    assert len(data["folders"]) == 1
    assert data["folders"][0]["name"] == "sub"
    assert len(data["photos"]) == 3


async def test_browse_skips_non_images(auth_client):
    r = await auth_client.get("/api/admin/browse")
    names = [p["name"] for p in r.json()["photos"]]
    assert "not_an_image.txt" not in names


async def test_browse_subfolder(auth_client):
    r = await auth_client.get("/api/admin/browse?path=sub")
    assert r.status_code == 200
    data = r.json()
    assert len(data["photos"]) == 1
    assert data["photos"][0]["name"] == "nested.jpg"


async def test_browse_child_count(auth_client):
    r = await auth_client.get("/api/admin/browse")
    folder = r.json()["folders"][0]
    # sub/ 안에 nested.jpg 1개
    assert folder["child_count"] == 1


async def test_browse_photo_has_thumb_url(auth_client):
    r = await auth_client.get("/api/admin/browse")
    photo = r.json()["photos"][0]
    assert "thumb_url" in photo
    assert photo["thumb_url"].startswith("/api/admin/thumb")


async def test_browse_path_traversal_blocked(auth_client):
    r = await auth_client.get("/api/admin/browse?path=../../etc")
    assert r.status_code == 400


async def test_browse_nonexistent_path(auth_client):
    r = await auth_client.get("/api/admin/browse?path=does_not_exist")
    assert r.status_code == 404


async def test_browse_requires_auth(client):
    r = await client.get("/api/admin/browse")
    assert r.status_code == 401


# ── search ────────────────────────────────────────────────────────────────────

async def test_search_all(auth_client):
    r = await auth_client.get("/api/admin/search")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 4  # photo0,1,2 + nested
    assert data["page"] == 1


async def test_search_by_name(auth_client):
    r = await auth_client.get("/api/admin/search?q=photo0")
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "photo0.jpg"


async def test_search_by_name_case_insensitive(auth_client):
    r = await auth_client.get("/api/admin/search?q=PHOTO")
    data = r.json()
    assert data["total"] == 3


async def test_search_in_subfolder(auth_client):
    r = await auth_client.get("/api/admin/search?folder=sub")
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "nested.jpg"


async def test_search_pagination(auth_client):
    r = await auth_client.get("/api/admin/search?size=2&page=2")
    data = r.json()
    assert data["total"] == 4
    assert len(data["items"]) == 2
    assert data["page"] == 2


async def test_search_requires_auth(client):
    r = await client.get("/api/admin/search")
    assert r.status_code == 401


# ── thumb ─────────────────────────────────────────────────────────────────────

async def test_thumb_returns_image(auth_client):
    r = await auth_client.get("/api/admin/thumb?path=photo0.jpg&size=small")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"


async def test_thumb_invalid_size(auth_client):
    r = await auth_client.get("/api/admin/thumb?path=photo0.jpg&size=huge")
    assert r.status_code == 400


async def test_thumb_path_traversal_blocked(auth_client):
    r = await auth_client.get("/api/admin/thumb?path=../../etc/passwd&size=small")
    assert r.status_code == 400


async def test_thumb_nonexistent_file(auth_client):
    r = await auth_client.get("/api/admin/thumb?path=no_such.jpg&size=small")
    assert r.status_code == 404


async def test_thumb_requires_auth(client):
    r = await client.get("/api/admin/thumb?path=photo0.jpg&size=small")
    assert r.status_code == 401


async def test_thumb_absolute_path(auth_client, photo_root):
    """절대 경로로 관리자 썸네일 요청 시 정상 응답."""
    abs_path = str(photo_root / "photo0.jpg")
    r = await auth_client.get(f"/api/admin/thumb?path={abs_path}&size=small")
    assert r.status_code == 200


# ── photo (원본 이미지 서빙) ────────────────────────────────────────────────────

async def test_photo_returns_original_image(auth_client):
    r = await auth_client.get("/api/admin/photo?path=photo0.jpg")
    assert r.status_code == 200


async def test_photo_path_traversal_blocked(auth_client):
    r = await auth_client.get("/api/admin/photo?path=../../etc/passwd")
    assert r.status_code == 400


async def test_photo_nonexistent_file(auth_client):
    r = await auth_client.get("/api/admin/photo?path=no_such.jpg")
    assert r.status_code == 404


async def test_photo_requires_auth(client):
    r = await client.get("/api/admin/photo?path=photo0.jpg")
    assert r.status_code == 401


async def test_photo_absolute_path(auth_client, photo_root):
    """절대 경로로 관리자 원본 사진 요청 시 정상 응답."""
    abs_path = str(photo_root / "photo0.jpg")
    r = await auth_client.get(f"/api/admin/photo?path={abs_path}")
    assert r.status_code == 200


# ── browse hidden paths ───────────────────────────────────────────────────────

async def test_browse_hidden_folder_not_shown(auth_client, photo_root):
    private = photo_root / "private"
    private.mkdir()
    _make_jpg(private / "secret.jpg")

    await auth_client.patch("/api/admin/settings", json={"browse_hidden_paths": ["private"]})

    r = await auth_client.get("/api/admin/browse")
    folder_names = [f["name"] for f in r.json()["folders"]]
    assert "private" not in folder_names
    assert "sub" in folder_names


async def test_search_excludes_photos_under_hidden_path(auth_client, photo_root):
    private = photo_root / "private"
    private.mkdir()
    _make_jpg(private / "secret.jpg")

    await auth_client.patch("/api/admin/settings", json={"browse_hidden_paths": ["private"]})

    r = await auth_client.get("/api/admin/search")
    names = [item["name"] for item in r.json()["items"]]
    assert "secret.jpg" not in names
    assert any("photo" in n for n in names)


async def test_browse_hidden_path_segment_boundary(auth_client, photo_root):
    """'private' 숨김 설정이 'privatefoo' 폴더에는 적용되지 않아야 한다."""
    privatefoo = photo_root / "privatefoo"
    privatefoo.mkdir()
    _make_jpg(privatefoo / "visible.jpg")

    await auth_client.patch("/api/admin/settings", json={"browse_hidden_paths": ["private"]})

    r = await auth_client.get("/api/admin/browse")
    folder_names = [f["name"] for f in r.json()["folders"]]
    assert "privatefoo" in folder_names


# ── path-exists ───────────────────────────────────────────────────────────────

async def test_path_exists_existing_dir(auth_client, photo_root):
    r = await auth_client.get("/api/admin/path-exists?path=sub")
    assert r.status_code == 200
    assert r.json()["exists"] is True


async def test_path_exists_nonexistent(auth_client):
    r = await auth_client.get("/api/admin/path-exists?path=no_such_folder")
    assert r.status_code == 200
    assert r.json()["exists"] is False


async def test_path_exists_traversal_blocked(auth_client):
    r = await auth_client.get("/api/admin/path-exists?path=../../etc")
    assert r.status_code == 200
    assert r.json()["exists"] is False


async def test_path_exists_requires_auth(client):
    r = await client.get("/api/admin/path-exists?path=sub")
    assert r.status_code == 401


# ── list_music ────────────────────────────────────────────────────────────────

async def test_list_music_empty_when_no_dir(auth_client):
    r = await auth_client.get("/api/admin/music")
    assert r.status_code == 200
    assert r.json()["files"] == []


async def test_list_music_returns_audio_files(auth_client, tmp_path, monkeypatch):
    music_dir = tmp_path / "data" / "music"
    music_dir.mkdir(parents=True)
    (music_dir / "track.mp3").write_bytes(b"fake")
    (music_dir / "song.flac").write_bytes(b"fake")

    r = await auth_client.get("/api/admin/music")
    assert r.status_code == 200
    files = r.json()["files"]
    names = {f["name"] for f in files}
    assert names == {"track.mp3", "song.flac"}


async def test_list_music_filters_non_audio(auth_client, tmp_path):
    music_dir = tmp_path / "data" / "music"
    music_dir.mkdir(parents=True)
    (music_dir / "track.mp3").write_bytes(b"fake")
    (music_dir / "readme.txt").write_text("skip")
    (music_dir / "cover.jpg").write_bytes(b"skip")

    r = await auth_client.get("/api/admin/music")
    files = r.json()["files"]
    assert len(files) == 1
    assert files[0]["name"] == "track.mp3"


async def test_list_music_rel_path_format(auth_client, tmp_path):
    music_dir = tmp_path / "data" / "music" / "sub"
    music_dir.mkdir(parents=True)
    (music_dir / "track.mp3").write_bytes(b"fake")

    r = await auth_client.get("/api/admin/music")
    files = r.json()["files"]
    assert len(files) == 1
    assert files[0]["rel"] == "sub/track.mp3"


async def test_list_music_requires_auth(client):
    r = await client.get("/api/admin/music")
    assert r.status_code == 401


# ── search 페이지네이션 최적화 (날짜 필터 없을 때 해당 페이지만 enrich) ─────────

async def test_search_no_date_filter_pagination_returns_correct_total(auth_client):
    """날짜 필터 없이 페이지 크기 1로 조회해도 total은 전체 개수를 반환한다."""
    r = await auth_client.get("/api/admin/search?size=1&page=1")
    data = r.json()
    assert data["total"] == 4  # photo0,1,2 + nested
    assert len(data["items"]) == 1


async def test_search_no_date_filter_second_page(auth_client):
    """페이지 2는 1페이지와 다른 항목을 반환한다."""
    r1 = await auth_client.get("/api/admin/search?size=1&page=1")
    r2 = await auth_client.get("/api/admin/search?size=1&page=2")
    assert r1.json()["items"][0]["name"] != r2.json()["items"][0]["name"]


# ── photo_meta_cache IN 쿼리 (N+1 제거) ──────────────────────────────────────

async def test_browse_caches_exif_metadata(auth_client):
    """browse 두 번 호출 시 두 번째는 캐시 히트 (결과가 동일해야 한다)."""
    r1 = await auth_client.get("/api/admin/browse")
    r2 = await auth_client.get("/api/admin/browse")
    photos1 = sorted(r1.json()["photos"], key=lambda p: p["name"])
    photos2 = sorted(r2.json()["photos"], key=lambda p: p["name"])
    assert photos1 == photos2


# ── EXIF 재발 방지 테스트 ─────────────────────────────────────────────────────

async def test_browse_exif_taken_at_returned(auth_client, photo_root):
    """실제 EXIF DateTime이 있는 사진에서 taken_at이 올바르게 반환된다."""
    _make_jpg_with_exif(photo_root / "dated.jpg", "2023:05:15 10:30:00")

    r = await auth_client.get("/api/admin/browse")
    assert r.status_code == 200
    photos = {p["name"]: p for p in r.json()["photos"]}
    assert "dated.jpg" in photos
    p = photos["dated.jpg"]
    assert p["taken_at"] is not None, "EXIF taken_at이 반환되어야 함"
    assert p["taken_at"].startswith("2023-05-15")
    assert p["width"] == 100


async def test_failed_exif_not_cached(auth_client, monkeypatch):
    """get_image_meta 실패(width=None) 결과는 캐시에 저장하지 않아 다음 요청에 재시도한다."""
    from backend.services import photo_meta
    from backend.services.thumbnail import _EMPTY_META, get_image_meta as real_get_meta

    # 1차 browse: EXIF 읽기 실패 시뮬레이션
    monkeypatch.setattr(photo_meta, "get_image_meta", lambda fp: dict(_EMPTY_META))
    r1 = await auth_client.get("/api/admin/browse")
    assert r1.status_code == 200
    assert all(p["width"] is None for p in r1.json()["photos"]), "실패 시 width=None이어야 함"

    # 원래 함수 복구
    monkeypatch.setattr(photo_meta, "get_image_meta", real_get_meta)

    # 2차 browse: 실패 결과가 캐시되지 않았으므로 재시도해 실제 EXIF를 읽어야 함
    r2 = await auth_client.get("/api/admin/browse")
    assert r2.status_code == 200
    assert all(p["width"] == 100 for p in r2.json()["photos"]), "재시도 후 width가 실제 값(100)이어야 함"


# ── search 전체 트리 walk 캐시 (P1) ─────────────────────────────────────────────

async def test_search_walk_cache_hides_new_file_within_ttl(auth_client, photo_root):
    """캐시 TTL 내 새로 추가된 파일은 반영되지 않고, 캐시 만료 후에는 반영돼야 한다."""
    from backend.routers import admin_browse

    admin_browse._walk_cache.clear()
    r1 = await auth_client.get("/api/admin/search")
    total1 = r1.json()["total"]

    _make_jpg(photo_root / "new_during_ttl.jpg")
    r2 = await auth_client.get("/api/admin/search")
    assert r2.json()["total"] == total1, "TTL 내에는 캐시된 walk 결과를 재사용해야 함"

    admin_browse._walk_cache.clear()  # TTL 만료를 흉내
    r3 = await auth_client.get("/api/admin/search")
    assert r3.json()["total"] == total1 + 1, "캐시 만료 후에는 새 파일이 반영돼야 함"


# ── EXIF 읽기 동시성 제한 (P1) ───────────────────────────────────────────────────

async def test_load_photo_meta_respects_exif_concurrency_limit(client, monkeypatch):
    """캐시 미스 EXIF 읽기가 세마포어 한도를 넘어 동시 실행되면 안 된다."""
    import asyncio
    import threading
    import time as time_mod

    from backend.models.database import get_db
    from backend.services import photo_meta

    monkeypatch.setattr(photo_meta, "_exif_read_semaphore", asyncio.Semaphore(2))

    current = 0
    peak = 0
    counter_lock = threading.Lock()

    def slow_get_image_meta(path):
        nonlocal current, peak
        with counter_lock:
            current += 1
            peak = max(peak, current)
        time_mod.sleep(0.05)
        with counter_lock:
            current -= 1
        return {
            "width": 10, "height": 10, "taken_at": None,
            "make": None, "camera": None, "software": None,
            "shutter": None, "aperture": None, "iso": None, "focal_length": None,
            "shoot_mode": None, "flash": None, "metering": None, "exposure_mode": None,
        }

    monkeypatch.setattr(photo_meta, "get_image_meta", slow_get_image_meta)

    rels = [f"nofile_{i}.jpg" for i in range(8)]
    db_gen = get_db()
    db = await db_gen.__anext__()
    try:
        await photo_meta.load_photo_meta(rels, db)
    finally:
        await db_gen.aclose()

    assert peak <= 2
