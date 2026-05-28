import os

import pytest_asyncio
from PIL import Image


# ── 픽스처 ──────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def media_env(admin_client, tmp_path):
    """이미지 파일 + 앨범 + 공유 링크 + 세션 쿠키 세팅."""
    photo_path = (tmp_path / "photos" / "test.jpg").as_posix()
    Image.new("RGB", (200, 150), color=(100, 150, 200)).save(photo_path, "JPEG")

    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "Media Test", "photo_paths": [photo_path]},
    )
    album_id = r.json()["id"]
    r = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    token = r.json()["token"]
    await admin_client.post(f"/api/share/{token}/auth", json={})

    return {"token": token, "photo_path": photo_path, "album_id": album_id}


@pytest_asyncio.fixture
async def music_env(admin_client, tmp_path):
    """음악 파일 + 앨범 + 공유 링크 + 세션 쿠키 세팅."""
    music_dir = tmp_path / "data" / "music"
    music_dir.mkdir(parents=True, exist_ok=True)
    music_path = (music_dir / "bg.mp3").as_posix()
    (music_dir / "bg.mp3").write_bytes(b"ID3fake")

    r = await admin_client.post("/api/admin/albums", json={"name": "Music Test", "photo_paths": []})
    album_id = r.json()["id"]
    await admin_client.patch(f"/api/admin/albums/{album_id}", json={"music_path": music_path})

    r = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    token = r.json()["token"]
    await admin_client.post(f"/api/share/{token}/auth", json={})

    return {"token": token, "music_path": music_path}


# ── /thumb ─────────────────────────────────────────────────────────────────────

async def test_thumb_small_returns_jpeg(admin_client, media_env):
    path = media_env["photo_path"]
    r = await admin_client.get(f"/thumb/{path}?size=small")
    assert r.status_code == 200
    assert "image/jpeg" in r.headers["content-type"]


async def test_thumb_medium(admin_client, media_env):
    path = media_env["photo_path"]
    r = await admin_client.get(f"/thumb/{path}?size=medium")
    assert r.status_code == 200


async def test_thumb_invalid_size(admin_client, media_env):
    path = media_env["photo_path"]
    r = await admin_client.get(f"/thumb/{path}?size=huge")
    assert r.status_code == 400


async def test_thumb_no_cookie(admin_client, tmp_path):
    """세션 쿠키 없이 요청 → 401."""
    photo_path = (tmp_path / "photos" / "nc.jpg").as_posix()
    Image.new("RGB", (50, 50)).save(photo_path, "JPEG")
    await admin_client.post("/api/admin/albums", json={"name": "NC", "photo_paths": [photo_path]})
    # auth 미호출 → share_session 쿠키 없음
    r = await admin_client.get(f"/thumb/{photo_path}?size=small")
    assert r.status_code == 401


async def test_thumb_file_not_in_album(admin_client, media_env, tmp_path):
    """앨범에 없는 파일 → 403."""
    other = (tmp_path / "photos" / "other.jpg").as_posix()
    Image.new("RGB", (50, 50)).save(other, "JPEG")
    r = await admin_client.get(f"/thumb/{other}?size=small")
    assert r.status_code == 403


async def test_thumb_file_missing_on_disk(admin_client, media_env):
    """앨범에 등록됐으나 디스크에 없는 파일 → 404."""
    path = media_env["photo_path"]
    os.remove(path)
    r = await admin_client.get(f"/thumb/{path}?size=small")
    assert r.status_code == 404


# ── /media ─────────────────────────────────────────────────────────────────────

async def test_media_returns_image_bytes(admin_client, media_env):
    path = media_env["photo_path"]
    r = await admin_client.get(f"/media/{path}")
    assert r.status_code == 200
    assert len(r.content) > 0


async def test_media_no_cookie(admin_client, tmp_path):
    """세션 쿠키 없이 요청 → 401."""
    photo_path = (tmp_path / "photos" / "nc2.jpg").as_posix()
    Image.new("RGB", (50, 50)).save(photo_path, "JPEG")
    await admin_client.post("/api/admin/albums", json={"name": "NC2", "photo_paths": [photo_path]})
    r = await admin_client.get(f"/media/{photo_path}")
    assert r.status_code == 401


async def test_media_file_not_in_album(admin_client, media_env, tmp_path):
    """앨범에 없는 파일 → 403."""
    other = (tmp_path / "photos" / "outsider.jpg").as_posix()
    Image.new("RGB", (50, 50)).save(other, "JPEG")
    r = await admin_client.get(f"/media/{other}")
    assert r.status_code == 403


async def test_media_file_missing_on_disk(admin_client, media_env):
    """앨범에 등록됐으나 디스크에 없는 파일 → 404."""
    path = media_env["photo_path"]
    os.remove(path)
    r = await admin_client.get(f"/media/{path}")
    assert r.status_code == 404


async def test_media_cross_token_denied(admin_client, tmp_path):
    """token1 쿠키로 token2 앨범 파일에 접근 → 403."""
    p1 = (tmp_path / "photos" / "p1.jpg").as_posix()
    Image.new("RGB", (50, 50)).save(p1, "JPEG")
    r = await admin_client.post("/api/admin/albums", json={"name": "A1", "photo_paths": [p1]})
    r = await admin_client.post(f"/api/admin/albums/{r.json()['id']}/links", json={})
    token1 = r.json()["token"]
    await admin_client.post(f"/api/share/{token1}/auth", json={})  # token1 쿠키 발급

    p2 = (tmp_path / "photos" / "p2.jpg").as_posix()
    Image.new("RGB", (50, 50)).save(p2, "JPEG")
    r = await admin_client.post("/api/admin/albums", json={"name": "A2", "photo_paths": [p2]})

    # token1 쿠키로 token2 앨범 파일 요청
    r = await admin_client.get(f"/media/{p2}")
    assert r.status_code == 403


# ── /music ─────────────────────────────────────────────────────────────────────

async def test_music_returns_file(admin_client, music_env):
    token = music_env["token"]
    r = await admin_client.get(f"/music/{token}")
    assert r.status_code == 200


async def test_music_no_cookie(admin_client):
    """세션 쿠키 없이 요청 → 401."""
    r = await admin_client.post("/api/admin/albums", json={"name": "MNC", "photo_paths": []})
    album_id = r.json()["id"]
    r = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    token = r.json()["token"]
    # auth 미호출 → 401
    r = await admin_client.get(f"/music/{token}")
    assert r.status_code == 401


async def test_music_no_music_path(admin_client, media_env):
    """앨범에 음악이 없으면 → 404."""
    token = media_env["token"]
    r = await admin_client.get(f"/music/{token}")
    assert r.status_code == 404


async def test_music_file_missing_on_disk(admin_client, music_env):
    """DB에 등록됐으나 파일이 디스크에 없으면 → 404."""
    os.remove(music_env["music_path"])
    r = await admin_client.get(f"/music/{music_env['token']}")
    assert r.status_code == 404
