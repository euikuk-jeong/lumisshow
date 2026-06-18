import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image


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
