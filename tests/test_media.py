import os
import shutil
from pathlib import Path

import pytest_asyncio
from mutagen.id3 import ID3, APIC
from PIL import Image

_BUNDLED_SAMPLE = (
    Path(__file__).resolve().parent.parent
    / "frontend" / "assets" / "music" / "bundled" / "paulyudin-emotional-emotional-music-573976.mp3"
)


# ── 픽스처 ──────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def media_env(admin_client, tmp_path):
    """이미지 파일 + 앨범 + 공유 링크 + 세션 쿠키 세팅."""
    photo_dir = tmp_path / "photos"
    photo_dir.mkdir(parents=True, exist_ok=True)
    abs_path = str(photo_dir / "test.jpg")
    Image.new("RGB", (200, 150), color=(100, 150, 200)).save(abs_path, "JPEG")

    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "Media Test", "photo_paths": [abs_path]},
    )
    album_id = r.json()["id"]

    # DB에 저장된 상대 경로 취득 (예: "test.jpg")
    album_data = (await admin_client.get(f"/api/admin/albums/{album_id}")).json()
    stored_path = album_data["photos"][0]["file_path"]

    r = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    token = r.json()["token"]
    await admin_client.post(f"/api/share/{token}/auth", json={})

    return {"token": token, "stored_path": stored_path, "abs_path": abs_path, "album_id": album_id}


@pytest_asyncio.fixture
async def music_env(admin_client, tmp_path):
    """음악 파일 + 앨범 + 공유 링크 + 세션 쿠키 세팅."""
    music_dir = tmp_path / "data" / "music"
    music_dir.mkdir(parents=True, exist_ok=True)
    music_path = str(music_dir / "bg.mp3")
    (music_dir / "bg.mp3").write_bytes(b"ID3fake")

    r = await admin_client.post("/api/admin/albums", json={"name": "Music Test", "photo_paths": []})
    album_id = r.json()["id"]
    await admin_client.put(f"/api/admin/albums/{album_id}", json={"music_paths": [music_path]})

    r = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    token = r.json()["token"]
    await admin_client.post(f"/api/share/{token}/auth", json={})

    return {"token": token, "music_path": music_path}


# ── /thumb ─────────────────────────────────────────────────────────────────────

async def test_thumb_small_returns_jpeg(admin_client, media_env):
    path = media_env["stored_path"]
    r = await admin_client.get(f"/thumb/{path}?size=small")
    assert r.status_code == 200
    assert "image/jpeg" in r.headers["content-type"]


async def test_thumb_medium(admin_client, media_env):
    path = media_env["stored_path"]
    r = await admin_client.get(f"/thumb/{path}?size=medium")
    assert r.status_code == 200


async def test_thumb_large(admin_client, media_env):
    path = media_env["stored_path"]
    r = await admin_client.get(f"/thumb/{path}?size=large")
    assert r.status_code == 200


async def test_thumb_invalid_size(admin_client, media_env):
    path = media_env["stored_path"]
    r = await admin_client.get(f"/thumb/{path}?size=huge")
    assert r.status_code == 400


async def test_thumb_no_cookie(admin_client, tmp_path):
    """세션 쿠키 없이 요청 → 401."""
    photo_path = str(tmp_path / "photos" / "nc.jpg")
    Image.new("RGB", (50, 50)).save(photo_path, "JPEG")
    r = await admin_client.post("/api/admin/albums", json={"name": "NC", "photo_paths": [photo_path]})
    album_id = r.json()["id"]
    album_data = (await admin_client.get(f"/api/admin/albums/{album_id}")).json()
    stored = album_data["photos"][0]["file_path"]
    # auth 미호출 → share_session 쿠키 없음
    r = await admin_client.get(f"/thumb/{stored}?size=small")
    assert r.status_code == 401


async def test_thumb_file_not_in_album(admin_client, media_env, tmp_path):
    """앨범에 없는 파일 → 403."""
    other = str(tmp_path / "photos" / "other.jpg")
    Image.new("RGB", (50, 50)).save(other, "JPEG")
    r = await admin_client.post("/api/admin/albums", json={"name": "OtherAlbum", "photo_paths": [other]})
    album_id = r.json()["id"]
    album_data = (await admin_client.get(f"/api/admin/albums/{album_id}")).json()
    other_stored = album_data["photos"][0]["file_path"]
    # media_env 세션 쿠키로 다른 앨범 파일 요청 → 403
    r = await admin_client.get(f"/thumb/{other_stored}?size=small")
    assert r.status_code == 403


async def test_thumb_file_missing_on_disk(admin_client, media_env):
    """앨범에 등록됐으나 디스크에 없는 파일 → 404."""
    os.remove(media_env["abs_path"])
    r = await admin_client.get(f"/thumb/{media_env['stored_path']}?size=small")
    assert r.status_code == 404


# ── /media ─────────────────────────────────────────────────────────────────────

async def test_media_returns_image_bytes(admin_client, media_env):
    path = media_env["stored_path"]
    r = await admin_client.get(f"/media/{path}")
    assert r.status_code == 200
    assert len(r.content) > 0


async def test_media_range_request_returns_206(admin_client, media_env):
    """동영상 시킹 스트리밍이 의존하는 Range 지원 회귀 방지 — FileResponse가
    Range 헤더에 206 + Accept-Ranges + Content-Range로 응답해야 한다."""
    path = media_env["stored_path"]
    r = await admin_client.get(f"/media/{path}", headers={"Range": "bytes=0-9"})
    assert r.status_code == 206
    assert r.headers["accept-ranges"] == "bytes"
    assert "content-range" in r.headers
    assert len(r.content) == 10


async def test_media_no_cookie(admin_client, tmp_path):
    """세션 쿠키 없이 요청 → 401."""
    photo_path = str(tmp_path / "photos" / "nc2.jpg")
    Image.new("RGB", (50, 50)).save(photo_path, "JPEG")
    r = await admin_client.post("/api/admin/albums", json={"name": "NC2", "photo_paths": [photo_path]})
    album_id = r.json()["id"]
    album_data = (await admin_client.get(f"/api/admin/albums/{album_id}")).json()
    stored = album_data["photos"][0]["file_path"]
    r = await admin_client.get(f"/media/{stored}")
    assert r.status_code == 401


async def test_media_file_not_in_album(admin_client, media_env, tmp_path):
    """앨범에 없는 파일 → 403."""
    other = str(tmp_path / "photos" / "outsider.jpg")
    Image.new("RGB", (50, 50)).save(other, "JPEG")
    r = await admin_client.post("/api/admin/albums", json={"name": "OutsiderAlbum", "photo_paths": [other]})
    album_id = r.json()["id"]
    album_data = (await admin_client.get(f"/api/admin/albums/{album_id}")).json()
    other_stored = album_data["photos"][0]["file_path"]
    r = await admin_client.get(f"/media/{other_stored}")
    assert r.status_code == 403


async def test_media_file_missing_on_disk(admin_client, media_env):
    """앨범에 등록됐으나 디스크에 없는 파일 → 404."""
    os.remove(media_env["abs_path"])
    r = await admin_client.get(f"/media/{media_env['stored_path']}")
    assert r.status_code == 404


async def test_media_relative_path_resolved(admin_client, tmp_path):
    """Browse UI가 보내는 상대 경로(sub/p.jpg)로 추가한 사진을 /media/ 로 서빙 가능해야 한다."""
    sub = tmp_path / "photos" / "sub"
    sub.mkdir(parents=True, exist_ok=True)
    photo = sub / "p.jpg"
    Image.new("RGB", (50, 50)).save(str(photo), "JPEG")

    r = await admin_client.post("/api/admin/albums", json={"name": "RelTest", "photo_paths": ["sub/p.jpg"]})
    album_id = r.json()["id"]
    r = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    token = r.json()["token"]
    await admin_client.post(f"/api/share/{token}/auth", json={})

    album_detail = (await admin_client.get(f"/api/admin/albums/{album_id}")).json()
    stored_path = album_detail["photos"][0]["file_path"]
    r = await admin_client.get(f"/media/{stored_path}")
    assert r.status_code == 200


async def test_thumb_path_traversal(admin_client, tmp_path):
    """PHOTO_ROOT 밖 파일이 DB에 등록됐더라도 /thumb/ 접근 → 403."""
    secret = tmp_path / "secret.jpg"
    Image.new("RGB", (50, 50)).save(str(secret), "JPEG")
    secret_posix = secret.as_posix()

    r = await admin_client.post("/api/admin/albums", json={"name": "Traversal T", "photo_paths": [secret_posix]})
    album_id = r.json()["id"]
    r = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    token = r.json()["token"]
    await admin_client.post(f"/api/share/{token}/auth", json={})

    # 절대 경로로 요청 → media router가 상대 경로로 정규화 → DB 매칭 → path traversal check → 403
    r = await admin_client.get(f"/thumb/{secret_posix}?size=small")
    assert r.status_code == 403


async def test_media_path_traversal(admin_client, tmp_path):
    """PHOTO_ROOT 밖 파일이 DB에 등록됐더라도 /media/ 접근 → 403."""
    secret = tmp_path / "secret2.jpg"
    Image.new("RGB", (50, 50)).save(str(secret), "JPEG")
    secret_posix = secret.as_posix()

    r = await admin_client.post("/api/admin/albums", json={"name": "Traversal M", "photo_paths": [secret_posix]})
    album_id = r.json()["id"]
    r = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    token = r.json()["token"]
    await admin_client.post(f"/api/share/{token}/auth", json={})

    r = await admin_client.get(f"/media/{secret_posix}")
    assert r.status_code == 403


async def test_media_cross_token_denied(admin_client, tmp_path):
    """token1 쿠키로 token2 앨범 파일에 접근 → 403."""
    p1 = str(tmp_path / "photos" / "p1.jpg")
    Image.new("RGB", (50, 50)).save(p1, "JPEG")
    r = await admin_client.post("/api/admin/albums", json={"name": "A1", "photo_paths": [p1]})
    album1_id = r.json()["id"]
    r = await admin_client.post(f"/api/admin/albums/{album1_id}/links", json={})
    token1 = r.json()["token"]
    await admin_client.post(f"/api/share/{token1}/auth", json={})  # token1 쿠키 발급

    p2 = str(tmp_path / "photos" / "p2.jpg")
    Image.new("RGB", (50, 50)).save(p2, "JPEG")
    r = await admin_client.post("/api/admin/albums", json={"name": "A2", "photo_paths": [p2]})
    album2_id = r.json()["id"]

    # A2 앨범의 저장 경로 취득
    album2_data = (await admin_client.get(f"/api/admin/albums/{album2_id}")).json()
    p2_stored = album2_data["photos"][0]["file_path"]

    # token1 쿠키로 token2 앨범 파일 요청 → 403
    r = await admin_client.get(f"/media/{p2_stored}")
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


# ── /music/{token}/cover ───────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def music_cover_env(admin_client, tmp_path):
    """ID3 APIC(커버 이미지) 프레임이 있는 실제 mp3 + 앨범 + 공유 링크 + 세션 쿠키 세팅."""
    music_dir = tmp_path / "data" / "music"
    music_dir.mkdir(parents=True, exist_ok=True)
    music_path = music_dir / "cover.mp3"
    shutil.copy(_BUNDLED_SAMPLE, music_path)
    tags = ID3(music_path)
    tags.delall("APIC")  # 번들 mp3에 이미 심어둔 실제 커버를 지우고 테스트용 고정 바이트로 교체
    tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=b"\xff\xd8\xff\xd9fakejpeg"))
    tags.save(music_path)

    r = await admin_client.post("/api/admin/albums", json={"name": "Music Cover Test", "photo_paths": []})
    album_id = r.json()["id"]
    await admin_client.put(f"/api/admin/albums/{album_id}", json={"music_paths": [str(music_path)]})

    r = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    token = r.json()["token"]
    await admin_client.post(f"/api/share/{token}/auth", json={})

    return {"token": token, "music_path": str(music_path)}


async def test_music_cover_returns_image_bytes(admin_client, music_cover_env):
    token = music_cover_env["token"]
    r = await admin_client.get(f"/music/{token}/cover")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.content == b"\xff\xd8\xff\xd9fakejpeg"


async def test_music_cover_no_cover_returns_404(admin_client, music_env):
    """실제 mp3지만 임베디드 커버가 없으면 → 404."""
    token = music_env["token"]
    r = await admin_client.get(f"/music/{token}/cover")
    assert r.status_code == 404


async def test_music_cover_no_cookie(admin_client):
    """세션 쿠키 없이 요청 → 401."""
    r = await admin_client.post("/api/admin/albums", json={"name": "MCNC", "photo_paths": []})
    album_id = r.json()["id"]
    r = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    token = r.json()["token"]
    # auth 미호출 → 401
    r = await admin_client.get(f"/music/{token}/cover")
    assert r.status_code == 401
