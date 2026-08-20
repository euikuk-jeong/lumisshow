import zipfile
from io import BytesIO

from PIL import Image


# ── 앨범 media_type 기록 (admin_albums.py) ─────────────────────────────────────

async def test_create_album_sets_media_type_photo_and_video(admin_client):
    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "Mixed", "photo_paths": ["a.jpg", "clip.mp4"]},
    )
    album_id = r.json()["id"]
    assert r.json()["photo_count"] == 1
    assert r.json()["video_count"] == 1

    detail = (await admin_client.get(f"/api/admin/albums/{album_id}")).json()
    by_name = {p["file_path"]: p["media_type"] for p in detail["photos"]}
    assert by_name["a.jpg"] == "photo"
    assert by_name["clip.mp4"] == "video"


async def test_add_photos_sets_media_type(admin_client):
    album_id = (await admin_client.post("/api/admin/albums", json={"name": "Add"})).json()["id"]
    await admin_client.post(f"/api/admin/albums/{album_id}/photos", json={"photo_paths": ["v.mov"]})
    detail = (await admin_client.get(f"/api/admin/albums/{album_id}")).json()
    assert detail["photos"][0]["media_type"] == "video"


async def test_update_album_rejects_video_cover_path(admin_client):
    """동영상을 커버로 지정하면 공유뷰어 cover_index 계산(사진만 대상)이 매칭
    실패해 첫 번째 사진으로 조용히 폴백하는 문제가 있었다 — API 레벨에서 차단."""
    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "CoverGuard", "photo_paths": ["a.jpg", "clip.mp4"]},
    )
    album_id = r.json()["id"]
    r = await admin_client.put(f"/api/admin/albums/{album_id}", json={"cover_path": "clip.mp4"})
    assert r.status_code == 400

    r = await admin_client.put(f"/api/admin/albums/{album_id}", json={"cover_path": "a.jpg"})
    assert r.status_code == 200
    assert r.json()["cover_path"] == "a.jpg"


async def test_duplicate_album_copies_media_type(admin_client):
    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "Src", "photo_paths": ["a.jpg", "b.webm"]},
    )
    album_id = r.json()["id"]
    dup = (await admin_client.post(f"/api/admin/albums/{album_id}/duplicate", json={"name": "Dup"})).json()
    assert dup["photo_count"] == 1
    assert dup["video_count"] == 1


async def test_list_albums_reports_video_count(admin_client):
    await admin_client.post(
        "/api/admin/albums",
        json={"name": "L", "photo_paths": ["a.jpg", "b.mp4", "c.m4v"]},
    )
    data = (await admin_client.get("/api/admin/albums")).json()
    assert data[0]["photo_count"] == 1
    assert data[0]["video_count"] == 2


async def test_empty_album_video_count_zero(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "Empty"})
    assert r.json()["photo_count"] == 0
    assert r.json()["video_count"] == 0


# ── 공유 응답: photos/videos 분리 ────────────────────────────────────────────────

async def _setup_mixed_link(admin_client):
    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "Mixed Share", "photo_paths": ["a.jpg", "clip.mp4"]},
    )
    album_id = r.json()["id"]
    r = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    token = r.json()["token"]
    await admin_client.post(f"/api/share/{token}/auth", json={})
    return token


async def test_share_photos_excludes_videos(admin_client):
    token = await _setup_mixed_link(admin_client)
    data = (await admin_client.get(f"/api/share/{token}/photos")).json()
    assert data["total"] == 1
    assert all(p["filename"] != "clip.mp4" for p in data["photos"])


async def test_share_videos_returns_only_videos(admin_client):
    token = await _setup_mixed_link(admin_client)
    data = (await admin_client.get(f"/api/share/{token}/videos")).json()
    assert data["total"] == 1
    assert data["videos"][0]["filename"] == "clip.mp4"
    assert data["videos"][0]["url"].startswith("/media/")


async def test_share_videos_without_auth(admin_client):
    r = await admin_client.post(
        "/api/admin/albums", json={"name": "NoAuth", "photo_paths": ["clip.mp4"]},
    )
    album_id = r.json()["id"]
    r = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    token = r.json()["token"]
    r = await admin_client.get(f"/api/share/{token}/videos")
    assert r.status_code == 401


async def test_share_album_reports_video_count(admin_client):
    token = await _setup_mixed_link(admin_client)
    data = (await admin_client.get(f"/api/share/{token}/album")).json()
    assert data["photo_count"] == 1
    assert data["video_count"] == 1


# ── 동영상 ZIP 다운로드 ───────────────────────────────────────────────────────

async def test_download_videos_zip_without_auth(admin_client):
    r = await admin_client.post(
        "/api/admin/albums", json={"name": "DVNoAuth", "photo_paths": ["clip.mp4"]},
    )
    album_id = r.json()["id"]
    r = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    token = r.json()["token"]
    r = await admin_client.get(f"/api/share/{token}/download-videos")
    assert r.status_code == 401


async def test_download_videos_zip_no_videos_returns_404(admin_client):
    r = await admin_client.post(
        "/api/admin/albums", json={"name": "NoVideos", "photo_paths": ["a.jpg"]},
    )
    album_id = r.json()["id"]
    r = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    token = r.json()["token"]
    await admin_client.post(f"/api/share/{token}/auth", json={})
    r = await admin_client.get(f"/api/share/{token}/download-videos")
    assert r.status_code == 404


async def test_download_videos_zip_contains_only_videos(admin_client, tmp_path):
    photo_path = tmp_path / "photos" / "real.jpg"
    photo_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 40)).save(str(photo_path), "JPEG")
    video_path = tmp_path / "photos" / "real.mp4"
    video_path.write_bytes(b"fake mp4 bytes")

    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "ZipTest", "photo_paths": ["real.jpg", "real.mp4"]},
    )
    album_id = r.json()["id"]
    r = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    token = r.json()["token"]
    await admin_client.post(f"/api/share/{token}/auth", json={})

    r = await admin_client.get(f"/api/share/{token}/download-videos")
    assert r.status_code == 200
    assert "_videos.zip" in r.headers["content-disposition"]
    zf = zipfile.ZipFile(BytesIO(r.content))
    names = zf.namelist()
    assert names == ["real.mp4"]


async def test_download_zip_excludes_videos(admin_client, tmp_path):
    """사진 전체 다운로드(/download)에는 동영상이 섞이지 않아야 한다."""
    photo_path = tmp_path / "photos" / "p.jpg"
    photo_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 40)).save(str(photo_path), "JPEG")
    video_path = tmp_path / "photos" / "v.mp4"
    video_path.write_bytes(b"fake")

    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "PhotoZip", "photo_paths": ["p.jpg", "v.mp4"]},
    )
    album_id = r.json()["id"]
    r = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    token = r.json()["token"]
    await admin_client.post(f"/api/share/{token}/auth", json={})

    r = await admin_client.get(f"/api/share/{token}/download")
    assert r.status_code == 200
    zf = zipfile.ZipFile(BytesIO(r.content))
    assert zf.namelist() == ["p.jpg"]


# ── /media 동영상 서빙 (Content-Disposition inline) ────────────────────────────

async def test_media_video_served_inline(admin_client, tmp_path):
    video_path = tmp_path / "photos" / "inline.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"fake mp4 bytes")

    r = await admin_client.post(
        "/api/admin/albums", json={"name": "Inline", "photo_paths": ["inline.mp4"]},
    )
    album_id = r.json()["id"]
    r = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    token = r.json()["token"]
    await admin_client.post(f"/api/share/{token}/auth", json={})

    r = await admin_client.get("/media/inline.mp4")
    assert r.status_code == 200
    assert "inline" in r.headers["content-disposition"]


# ── 브라우즈: 동영상도 스캔 대상 ─────────────────────────────────────────────────

async def test_browse_lists_videos_with_media_type(admin_client, tmp_path):
    photo_root = tmp_path / "photos"  # conftest의 client fixture가 PHOTO_ROOT로 지정한 경로
    Image.new("RGB", (30, 30)).save(str(photo_root / "p.jpg"), "JPEG")
    (photo_root / "v.mp4").write_bytes(b"fake")

    r = await admin_client.get("/api/admin/browse")
    assert r.status_code == 200
    by_name = {p["name"]: p["media_type"] for p in r.json()["photos"]}
    assert by_name["p.jpg"] == "photo"
    assert by_name["v.mp4"] == "video"
