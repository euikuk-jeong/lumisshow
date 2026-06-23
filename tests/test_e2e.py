"""E2E 테스트: 실 uvicorn 서버 기반으로 주요 사용자 플로우를 검증한다."""
import io
import os
import socket
import threading
import time
import zipfile

import httpx
import pytest
from PIL import Image


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    """실 uvicorn 서버를 모듈 단위로 한 번 실행."""
    import uvicorn

    tmp = tmp_path_factory.mktemp("e2e")
    photo_dir = tmp / "photos"
    photo_dir.mkdir(parents=True, exist_ok=True)

    photo_path = (photo_dir / "sample.jpg").as_posix()
    Image.new("RGB", (400, 300), color=(80, 120, 160)).save(photo_path, "JPEG")

    port = _free_port()
    env_patch = {
        "DATA_DIR": str(tmp / "data"),
        "PHOTO_ROOT": str(photo_dir),
        "ADMIN_PASSWORD": "e2epass",
        "JWT_SECRET": "e2esecret",
        "BASE_URL": f"http://127.0.0.1:{port}",
    }
    saved = {k: os.environ.get(k) for k in env_patch}
    os.environ.update(env_patch)

    config = uvicorn.Config(
        "backend.main:app",
        host="127.0.0.1",
        port=port,
        log_level="error",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 10.0
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=1.0).status_code == 200:
                break
        except Exception:
            time.sleep(0.1)
    else:
        server.should_exit = True
        pytest.fail("E2E server failed to start within 10 seconds")

    yield {"url": f"http://127.0.0.1:{port}", "photo_path": photo_path}

    server.should_exit = True
    thread.join(timeout=5)

    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# ── 플로우 1: 전체 admin-to-viewer 플로우 ─────────────────────────────────────

async def test_complete_album_share_viewer_flow(live_server):
    """
    admin 로그인 → 앨범 생성 → 공유 링크 → 뷰어 인증 → 앨범/사진 조회
    → share.py 생성 URL로 media.py 미디어 접근까지 전체 검증.
    """
    url = live_server["url"]
    photo_path = live_server["photo_path"]

    async with httpx.AsyncClient(base_url=url, timeout=10.0) as c:
        # 1. admin 로그인
        r = await c.post("/api/auth/login", json={"password": "e2epass"})
        assert r.status_code == 200
        auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

        # 2. 앨범 생성 (사진 포함)
        r = await c.post(
            "/api/admin/albums",
            json={"name": "E2E Album", "photo_paths": [photo_path]},
            headers=auth,
        )
        assert r.status_code == 201
        album_id = r.json()["id"]
        assert r.json()["photo_count"] == 1

        # 3. 공유 링크 생성
        r = await c.post(f"/api/admin/albums/{album_id}/links", json={}, headers=auth)
        assert r.status_code == 201
        share_token = r.json()["token"]
        assert r.json()["share_url"].startswith(url)

        # 4. 링크 정보 (패스워드 불필요 확인)
        r = await c.get(f"/api/share/{share_token}")
        assert r.status_code == 200
        assert r.json()["requires_password"] is False

        # 5. 뷰어 인증 → 세션 쿠키 발급
        r = await c.post(f"/api/share/{share_token}/auth", json={})
        assert r.status_code == 200
        assert "share_session" in c.cookies

        # 6. 앨범 정보 조회
        r = await c.get(f"/api/share/{share_token}/album")
        assert r.status_code == 200
        assert r.json()["album_name"] == "E2E Album"
        assert r.json()["photo_count"] == 1

        # 7. 사진 목록 조회 + URL 형식 검증
        r = await c.get(f"/api/share/{share_token}/photos")
        assert r.status_code == 200
        photos = r.json()["photos"]
        assert len(photos) == 1
        media_url = photos[0]["url"]
        thumb_url = photos[0]["thumb_small_url"]
        assert media_url.startswith("/media/")
        assert thumb_url.startswith("/thumb/")
        assert "size=small" in thumb_url

        # 8. share.py가 생성한 URL로 원본 이미지 접근
        r = await c.get(media_url)
        assert r.status_code == 200
        assert len(r.content) > 0

        # 9. share.py가 생성한 URL로 썸네일 접근
        r = await c.get(thumb_url)
        assert r.status_code == 200
        assert "image/jpeg" in r.headers["content-type"]


# ── 플로우 2: 패스워드 보호 링크 ──────────────────────────────────────────────

async def test_password_protected_link_flow(live_server):
    """잘못된 패스워드 → 401, 올바른 패스워드 → 앨범/미디어 접근 성공."""
    url = live_server["url"]
    photo_path = live_server["photo_path"]

    async with httpx.AsyncClient(base_url=url, timeout=10.0) as c:
        r = await c.post("/api/auth/login", json={"password": "e2epass"})
        auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = await c.post(
            "/api/admin/albums",
            json={"name": "Protected", "photo_paths": [photo_path]},
            headers=auth,
        )
        album_id = r.json()["id"]
        r = await c.post(
            f"/api/admin/albums/{album_id}/links",
            json={"password": "secret123"},
            headers=auth,
        )
        share_token = r.json()["token"]

        # 패스워드 필요 여부 확인
        assert (await c.get(f"/api/share/{share_token}")).json()["requires_password"] is True

        # 잘못된 패스워드 → 401
        r = await c.post(f"/api/share/{share_token}/auth", json={"password": "wrongpass"})
        assert r.status_code == 401

        # 올바른 패스워드 → 200 + 쿠키
        r = await c.post(f"/api/share/{share_token}/auth", json={"password": "secret123"})
        assert r.status_code == 200
        assert "share_session" in c.cookies

        # 쿠키로 앨범 조회 + 미디어 접근
        r = await c.get(f"/api/share/{share_token}/album")
        assert r.status_code == 200

        photos = (await c.get(f"/api/share/{share_token}/photos")).json()["photos"]
        assert (await c.get(photos[0]["url"])).status_code == 200


# ── 플로우 3: 링크 비활성화 후 접근 차단 ──────────────────────────────────────

async def test_link_deactivation_blocks_viewer(live_server):
    """링크 비활성화 후 동일 토큰으로 뷰어 인증 시 404 반환."""
    url = live_server["url"]

    async with httpx.AsyncClient(base_url=url, timeout=10.0) as c:
        r = await c.post("/api/auth/login", json={"password": "e2epass"})
        auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = await c.post(
            "/api/admin/albums",
            json={"name": "Revoke Test", "photo_paths": []},
            headers=auth,
        )
        album_id = r.json()["id"]
        r = await c.post(f"/api/admin/albums/{album_id}/links", json={}, headers=auth)
        link_id = r.json()["id"]
        share_token = r.json()["token"]

        # 링크 활성 상태에서 인증 성공
        r = await c.post(f"/api/share/{share_token}/auth", json={})
        assert r.status_code == 200
        assert (await c.get(f"/api/share/{share_token}/album")).status_code == 200

        # admin이 링크 비활성화
        r = await c.patch(
            f"/api/admin/albums/{album_id}/links/{link_id}",
            json={"is_active": False},
            headers=auth,
        )
        assert r.status_code == 200

        # 비활성화 후 새 인증 시도 → 404
        async with httpx.AsyncClient(base_url=url, timeout=10.0) as c2:
            r = await c2.post(f"/api/share/{share_token}/auth", json={})
            assert r.status_code == 404


# ── 플로우 4: 음악 포함 앨범 ────────────────────────────────────────────────

async def test_album_with_music_flow(live_server):
    """음악 설정 앨범: has_music=True, /music/{token} 접근 가능."""
    url = live_server["url"]
    data_dir = os.environ.get("DATA_DIR", "")
    music_dir = os.path.join(data_dir, "music")
    os.makedirs(music_dir, exist_ok=True)
    music_path = os.path.join(music_dir, "bg.mp3").replace("\\", "/")
    with open(music_path, "wb") as f:
        f.write(b"ID3fake")

    async with httpx.AsyncClient(base_url=url, timeout=10.0) as c:
        r = await c.post("/api/auth/login", json={"password": "e2epass"})
        auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = await c.post(
            "/api/admin/albums",
            json={"name": "Music Album", "photo_paths": []},
            headers=auth,
        )
        album_id = r.json()["id"]
        await c.put(
            f"/api/admin/albums/{album_id}",
            json={"music_paths": [music_path]},
            headers=auth,
        )
        r = await c.post(f"/api/admin/albums/{album_id}/links", json={}, headers=auth)
        share_token = r.json()["token"]

        await c.post(f"/api/share/{share_token}/auth", json={})

        r = await c.get(f"/api/share/{share_token}/album")
        assert r.json()["has_music"] is True

        r = await c.get(f"/music/{share_token}")
        assert r.status_code == 200


# ── 플로우 5: 실제 파일 ZIP 다운로드 ────────────────────────────────────────────

async def test_zip_download_with_real_files(live_server):
    """실제 사진 파일이 있는 앨범 ZIP 다운로드 시 유효한 ZIP 파일이 반환된다."""
    url = live_server["url"]
    photo_path = live_server["photo_path"]

    async with httpx.AsyncClient(base_url=url, timeout=15.0) as c:
        r = await c.post("/api/auth/login", json={"password": "e2epass"})
        auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = await c.post(
            "/api/admin/albums",
            json={"name": "ZIP Real", "photo_paths": [photo_path]},
            headers=auth,
        )
        album_id = r.json()["id"]
        r = await c.post(f"/api/admin/albums/{album_id}/links", json={}, headers=auth)
        share_token = r.json()["token"]
        await c.post(f"/api/share/{share_token}/auth", json={})

        r = await c.get(f"/api/share/{share_token}/download")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            assert "sample.jpg" in zf.namelist()


# ── 플로우 6: ZIP 중복 파일명 자동 처리 ─────────────────────────────────────────

async def test_zip_download_duplicate_filename_handling(live_server):
    """서로 다른 폴더의 동일 파일명 사진 2장이 ZIP에 포함될 때 파일명을 자동 분리한다."""
    url = live_server["url"]
    photo_dir = os.path.dirname(live_server["photo_path"])

    sub1 = os.path.join(photo_dir, "dup_sub1")
    sub2 = os.path.join(photo_dir, "dup_sub2")
    os.makedirs(sub1, exist_ok=True)
    os.makedirs(sub2, exist_ok=True)
    dup1 = os.path.join(sub1, "dup.jpg")
    dup2 = os.path.join(sub2, "dup.jpg")
    Image.new("RGB", (80, 80), color=(255, 0, 0)).save(dup1, "JPEG")
    Image.new("RGB", (80, 80), color=(0, 255, 0)).save(dup2, "JPEG")

    async with httpx.AsyncClient(base_url=url, timeout=15.0) as c:
        r = await c.post("/api/auth/login", json={"password": "e2epass"})
        auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = await c.post(
            "/api/admin/albums",
            json={"name": "Dup ZIP", "photo_paths": [dup1, dup2]},
            headers=auth,
        )
        album_id = r.json()["id"]
        r = await c.post(f"/api/admin/albums/{album_id}/links", json={}, headers=auth)
        share_token = r.json()["token"]
        await c.post(f"/api/share/{share_token}/auth", json={})

        r = await c.get(f"/api/share/{share_token}/download")
        assert r.status_code == 200
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            names = zf.namelist()
            assert len(names) == 2
            assert "dup.jpg" in names
            assert "dup_1.jpg" in names


# ── 플로우 7: 앨범 커버 → cover_index 반환 ─────────────────────────────────────

async def test_album_cover_index_in_share_response(live_server):
    """앨범 커버 사진 설정 시 공유 뷰어 앨범 응답에 올바른 cover_index가 반환된다."""
    url = live_server["url"]
    photo_dir = os.path.dirname(live_server["photo_path"])

    p2 = os.path.join(photo_dir, "cover_b.jpg")
    p3 = os.path.join(photo_dir, "cover_c.jpg")
    Image.new("RGB", (80, 80), color=(0, 0, 255)).save(p2, "JPEG")
    Image.new("RGB", (80, 80), color=(255, 255, 0)).save(p3, "JPEG")

    async with httpx.AsyncClient(base_url=url, timeout=10.0) as c:
        r = await c.post("/api/auth/login", json={"password": "e2epass"})
        auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = await c.post(
            "/api/admin/albums",
            json={"name": "Cover Idx", "photo_paths": [live_server["photo_path"], p2, p3]},
            headers=auth,
        )
        album_id = r.json()["id"]

        # 두 번째 사진을 커버로 설정
        album_detail = (await c.get(f"/api/admin/albums/{album_id}", headers=auth)).json()
        cover_path = album_detail["photos"][1]["file_path"]
        await c.put(f"/api/admin/albums/{album_id}", json={"cover_path": cover_path}, headers=auth)

        r = await c.post(f"/api/admin/albums/{album_id}/links", json={}, headers=auth)
        share_token = r.json()["token"]
        await c.post(f"/api/share/{share_token}/auth", json={})

        r = await c.get(f"/api/share/{share_token}/album")
        assert r.status_code == 200
        assert r.json()["cover_index"] == 1


# ── 플로우 8: 멀티 트랙 음악 인덱스 네비게이션 ────────────────────────────────────

async def test_multi_track_music_index_navigation(live_server):
    """멀티 트랙 음악 앨범에서 index 파라미터로 각 트랙에 접근하고 범위 초과 시 404."""
    url = live_server["url"]
    data_dir = os.environ.get("DATA_DIR", "")
    music_dir = os.path.join(data_dir, "music")
    os.makedirs(music_dir, exist_ok=True)

    track1 = os.path.join(music_dir, "multi_t1.mp3").replace("\\", "/")
    track2 = os.path.join(music_dir, "multi_t2.mp3").replace("\\", "/")
    with open(track1, "wb") as f:
        f.write(b"ID3track1")
    with open(track2, "wb") as f:
        f.write(b"ID3track2")

    async with httpx.AsyncClient(base_url=url, timeout=10.0) as c:
        r = await c.post("/api/auth/login", json={"password": "e2epass"})
        auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = await c.post(
            "/api/admin/albums",
            json={"name": "Multi Track", "photo_paths": []},
            headers=auth,
        )
        album_id = r.json()["id"]
        await c.put(
            f"/api/admin/albums/{album_id}",
            json={"music_paths": [track1, track2]},
            headers=auth,
        )
        r = await c.post(f"/api/admin/albums/{album_id}/links", json={}, headers=auth)
        share_token = r.json()["token"]
        await c.post(f"/api/share/{share_token}/auth", json={})

        assert (await c.get(f"/music/{share_token}?index=0")).status_code == 200
        assert (await c.get(f"/music/{share_token}?index=1")).status_code == 200
        assert (await c.get(f"/music/{share_token}?index=99")).status_code == 404


# ── 플로우 9: health / version / SPA 라우트 ──────────────────────────────────────

async def test_health_version_and_spa_routes(live_server):
    """/health, /version, SPA 라우트(/, /admin/*, /s/*)가 모두 200을 반환한다."""
    url = live_server["url"]
    async with httpx.AsyncClient(base_url=url, timeout=10.0) as c:
        r = await c.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

        r = await c.get("/version")
        assert r.status_code == 200
        assert "version" in r.json()

        assert (await c.get("/")).status_code == 200
        assert (await c.get("/admin/login")).status_code == 200
        assert (await c.get("/s/some-token")).status_code == 200


# ── 플로우 10: Admin 전역 설정 → 공유 뷰어 슬라이드쇼 기본값 반영 ─────────────────

async def test_admin_settings_propagate_to_viewer(live_server):
    """Admin 전역 설정이 앨범 수준 설정이 없을 때 공유 뷰어 슬라이드쇼 기본값으로 반영된다."""
    url = live_server["url"]
    async with httpx.AsyncClient(base_url=url, timeout=10.0) as c:
        r = await c.post("/api/auth/login", json={"password": "e2epass"})
        auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

        await c.patch(
            "/api/admin/settings",
            json={"slideshow_interval": 15, "slideshow_order": "random"},
            headers=auth,
        )

        r = await c.post("/api/admin/albums", json={"name": "Settings Album"}, headers=auth)
        album_id = r.json()["id"]
        r = await c.post(f"/api/admin/albums/{album_id}/links", json={}, headers=auth)
        share_token = r.json()["token"]
        await c.post(f"/api/share/{share_token}/auth", json={})

        r = await c.get(f"/api/share/{share_token}/album")
        assert r.status_code == 200
        defaults = r.json()["slideshow_defaults"]
        assert defaults["interval"] == 15
        assert defaults["order"] == "random"

        # 설정 복원
        await c.patch(
            "/api/admin/settings",
            json={"slideshow_interval": 5, "slideshow_order": "sequential"},
            headers=auth,
        )


# ── 플로우 11: 날짜 필터 검색 ─────────────────────────────────────────────────────

async def test_admin_search_date_filter(live_server):
    """날짜 필터(date_from/date_to)로 검색 시 지정 범위 내 사진만 반환된다."""
    url = live_server["url"]
    photo_dir = os.path.dirname(live_server["photo_path"])

    def _make_exif_jpg(path, date_str):
        img = Image.new("RGB", (100, 100))
        exif = img.getexif()
        exif[306] = date_str  # DateTime (IFD0 tag)
        img.save(path, "JPEG", exif=exif.tobytes())

    _make_exif_jpg(os.path.join(photo_dir, "date_2020.jpg"), "2020:06:15 10:00:00")
    _make_exif_jpg(os.path.join(photo_dir, "date_2024.jpg"), "2024:06:15 10:00:00")

    async with httpx.AsyncClient(base_url=url, timeout=15.0) as c:
        r = await c.post("/api/auth/login", json={"password": "e2epass"})
        auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

        # 2020년 범위 필터
        r = await c.get("/api/admin/search?date_from=2020-01-01&date_to=2020-12-31", headers=auth)
        assert r.status_code == 200
        names = [item["name"] for item in r.json()["items"]]
        assert "date_2020.jpg" in names
        assert "date_2024.jpg" not in names

        # 2024년 범위 필터
        r = await c.get("/api/admin/search?date_from=2024-01-01&date_to=2024-12-31", headers=auth)
        names = [item["name"] for item in r.json()["items"]]
        assert "date_2024.jpg" in names
        assert "date_2020.jpg" not in names
