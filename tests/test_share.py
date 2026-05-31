import pytest


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

async def _setup_link(admin_client, *, password=None, with_photos=False, expires_at=None):
    """앨범 + 공유 링크 생성, token 반환."""
    photo_paths = ["a.jpg", "b.jpg"] if with_photos else []
    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "Test Album", "photo_paths": photo_paths},
    )
    album_id = r.json()["id"]

    body = {}
    if password:
        body["password"] = password
    if expires_at:
        body["expires_at"] = expires_at

    r = await admin_client.post(f"/api/admin/albums/{album_id}/links", json=body)
    return r.json()["token"]


async def _auth(client, token, password=None):
    body = {"password": password} if password else {}
    return await client.post(f"/api/share/{token}/auth", json=body)


# ── 링크 정보 조회 ─────────────────────────────────────────────────────────────

async def test_get_link_info_no_password(admin_client):
    token = await _setup_link(admin_client)
    r = await admin_client.get(f"/api/share/{token}")
    assert r.status_code == 200
    assert r.json()["requires_password"] is False


async def test_get_link_info_with_password(admin_client):
    token = await _setup_link(admin_client, password="secret")
    r = await admin_client.get(f"/api/share/{token}")
    assert r.status_code == 200
    assert r.json()["requires_password"] is True


async def test_get_link_info_not_found(admin_client):
    r = await admin_client.get("/api/share/nonexistent-token")
    assert r.status_code == 404


# ── 인증 (쿠키 발급) ──────────────────────────────────────────────────────────

async def test_auth_no_password_link(admin_client):
    token = await _setup_link(admin_client)
    r = await _auth(admin_client, token)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert "share_session" in admin_client.cookies


async def test_auth_correct_password(admin_client):
    token = await _setup_link(admin_client, password="mypass")
    r = await _auth(admin_client, token, password="mypass")
    assert r.status_code == 200
    assert "share_session" in admin_client.cookies


async def test_auth_wrong_password(admin_client):
    token = await _setup_link(admin_client, password="mypass")
    r = await _auth(admin_client, token, password="wrong")
    assert r.status_code == 401


async def test_auth_missing_password_on_protected_link(admin_client):
    token = await _setup_link(admin_client, password="mypass")
    r = await _auth(admin_client, token)  # password=None
    assert r.status_code == 401


async def test_auth_brute_force_lockout(admin_client):
    """패스워드 5회 연속 실패 → 6번째 요청은 429."""
    token = await _setup_link(admin_client, password="secret")
    for _ in range(5):
        r = await _auth(admin_client, token, password="wrong")
        assert r.status_code == 401
    r = await _auth(admin_client, token, password="wrong")
    assert r.status_code == 429


async def test_auth_lockout_resets_on_success(admin_client):
    """4회 실패 후 올바른 패스워드 성공 → 카운터 리셋, 이후 재시도 가능."""
    token = await _setup_link(admin_client, password="secret")
    for _ in range(4):
        await _auth(admin_client, token, password="wrong")
    r = await _auth(admin_client, token, password="secret")
    assert r.status_code == 200
    r = await _auth(admin_client, token, password="wrong")
    assert r.status_code == 401


async def test_auth_expired_link(admin_client):
    token = await _setup_link(admin_client, expires_at="2000-01-01T00:00:00")
    r = await _auth(admin_client, token)
    assert r.status_code == 404


async def test_auth_inactive_link(admin_client):
    token = await _setup_link(admin_client)
    # 링크 비활성화
    r = await admin_client.get(f"/api/admin/albums/1/links")
    links = r.json()
    link_id = next(lk["id"] for lk in links if lk["token"] == token)
    await admin_client.patch(
        f"/api/admin/albums/1/links/{link_id}", json={"is_active": False}
    )
    r = await _auth(admin_client, token)
    assert r.status_code == 404


# ── 앨범 정보 ─────────────────────────────────────────────────────────────────

async def test_get_album_after_auth(admin_client):
    token = await _setup_link(admin_client, with_photos=True)
    await _auth(admin_client, token)

    r = await admin_client.get(f"/api/share/{token}/album")
    assert r.status_code == 200
    data = r.json()
    assert data["album_name"] == "Test Album"
    assert data["photo_count"] == 2
    assert data["has_music"] is False


async def test_get_album_without_auth(admin_client):
    token = await _setup_link(admin_client)
    r = await admin_client.get(f"/api/share/{token}/album")
    assert r.status_code == 401


async def test_get_album_wrong_token_cookie(admin_client):
    token1 = await _setup_link(admin_client)
    token2 = await _setup_link(admin_client)
    await _auth(admin_client, token1)  # token1 쿠키 발급
    r = await admin_client.get(f"/api/share/{token2}/album")  # token2에 접근 시도
    assert r.status_code == 401


# ── 사진 목록 ─────────────────────────────────────────────────────────────────

async def test_get_photos_after_auth(admin_client):
    token = await _setup_link(admin_client, with_photos=True)
    await _auth(admin_client, token)

    r = await admin_client.get(f"/api/share/{token}/photos")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    assert len(data["photos"]) == 2


async def test_get_photos_urls_format(admin_client):
    token = await _setup_link(admin_client, with_photos=True)
    await _auth(admin_client, token)

    photos = (await admin_client.get(f"/api/share/{token}/photos")).json()["photos"]
    for p in photos:
        assert p["url"].startswith("/media/")
        assert p["thumb_small_url"].startswith("/thumb/")
        assert p["thumb_medium_url"].startswith("/thumb/")
        assert "size=small" in p["thumb_small_url"]
        assert "size=medium" in p["thumb_medium_url"]


async def test_get_photos_without_auth(admin_client):
    token = await _setup_link(admin_client)
    r = await admin_client.get(f"/api/share/{token}/photos")
    assert r.status_code == 401


async def test_get_photos_empty_album(admin_client):
    token = await _setup_link(admin_client, with_photos=False)
    await _auth(admin_client, token)
    data = (await admin_client.get(f"/api/share/{token}/photos")).json()
    assert data["total"] == 0
    assert data["photos"] == []


# ── ZIP 다운로드 ──────────────────────────────────────────────────────────────

async def test_download_zip_without_auth(admin_client):
    token = await _setup_link(admin_client, with_photos=True)
    r = await admin_client.get(f"/api/share/{token}/download")
    assert r.status_code == 401


async def test_download_zip_empty_album(admin_client):
    token = await _setup_link(admin_client, with_photos=False)
    await _auth(admin_client, token)
    r = await admin_client.get(f"/api/share/{token}/download")
    assert r.status_code == 404


async def test_download_zip_with_photos(admin_client, tmp_path):
    # 실제 파일이 없으면 ZIP에 포함 안 됨 — 여기선 헤더와 스트리밍만 검증
    token = await _setup_link(admin_client, with_photos=True)
    await _auth(admin_client, token)
    r = await admin_client.get(f"/api/share/{token}/download")
    # a.jpg, b.jpg가 실제로 존재하지 않으므로 ZIP은 비어있지만 200 반환
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert "attachment" in r.headers["content-disposition"]
