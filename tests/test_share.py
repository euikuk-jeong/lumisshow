import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image


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


# ── 조회수 ────────────────────────────────────────────────────────────────────

async def _get_view_count(admin_client, album_id: int) -> int:
    r = await admin_client.get(f"/api/admin/albums/{album_id}")
    return r.json()["view_count"]


async def test_view_count_increments_on_first_access(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "A"})
    album_id = r.json()["id"]
    r = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    token = r.json()["token"]
    await _auth(admin_client, token)

    assert await _get_view_count(admin_client, album_id) == 0
    await admin_client.get(f"/api/share/{token}/album")
    assert await _get_view_count(admin_client, album_id) == 1


async def test_view_count_not_incremented_twice_same_session(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "A"})
    album_id = r.json()["id"]
    r = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    token = r.json()["token"]
    await _auth(admin_client, token)

    await admin_client.get(f"/api/share/{token}/album")
    await admin_client.get(f"/api/share/{token}/album")
    # 같은 세션 쿠키로 두 번 조회해도 1만 증가
    assert await _get_view_count(admin_client, album_id) == 1


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
        assert p["thumb_large_url"].startswith("/thumb/")
        assert "size=small" in p["thumb_small_url"]
        assert "size=medium" in p["thumb_medium_url"]
        assert "size=large" in p["thumb_large_url"]
        assert p["file_path"] is None  # 공유 링크에 원본 경로 미노출


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


async def test_get_photos_exposes_only_ai_path_manual_tags(admin_client):
    """정보 패널(i 버튼) 노출용 — 공유 링크는 ai/path/manual만 노출하고 person/location은
    데이터가 있어도 항상 빈 리스트여야 한다(doc/tagging_requirement.md 노출 범위 표,
    프라이버시/오매칭 이슈로 얼굴 인식 자체가 승인 큐를 거치는 것과 동일한 이유)."""
    import aiosqlite

    from backend.models.ai_database import _ai_db_path

    token = await _setup_link(admin_client, with_photos=True)
    await _auth(admin_client, token)

    async with aiosqlite.connect(_ai_db_path()) as db:
        await db.execute(
            "INSERT INTO photo_tags (photo_path, tag, source) VALUES "
            "('a.jpg', '지우', 'person'), "
            "('a.jpg', '서울', 'location'), "
            "('a.jpg', '캠핑', 'ai'), "
            "('a.jpg', '서울대공원', 'path'), "
            "('a.jpg', '눈사람', 'manual')"
        )
        await db.commit()

    photos = (await admin_client.get(f"/api/share/{token}/photos")).json()["photos"]
    photo = next(p for p in photos if p["url"] == "/media/a.jpg")
    assert photo["person_tags"] == []
    assert photo["location_tags"] == []
    assert photo["ai_tags"] == ["캠핑"]
    assert photo["path_tags"] == ["서울대공원"]
    assert photo["manual_tags"] == ["눈사람"]


async def test_get_photos_excludes_disabled_category_tags(admin_client):
    """사물 인식(AI 태그)을 끄면 공유 뷰어에서도 DB에 남은 ai 태그가 노출되면 안 된다."""
    import aiosqlite

    from backend.models.ai_database import _ai_db_path

    token = await _setup_link(admin_client, with_photos=True)
    await _auth(admin_client, token)

    async with aiosqlite.connect(_ai_db_path()) as db:
        await db.execute(
            "INSERT INTO photo_tags (photo_path, tag, source) VALUES "
            "('a.jpg', '캠핑', 'ai'), ('a.jpg', '서울대공원', 'path')"
        )
        await db.commit()

    await admin_client.patch("/api/admin/ai/settings", json={"ai_tag_enabled": False})
    photos = (await admin_client.get(f"/api/share/{token}/photos")).json()["photos"]
    photo = next(p for p in photos if p["url"] == "/media/a.jpg")
    assert photo["ai_tags"] == []
    assert photo["path_tags"] == ["서울대공원"]


async def test_get_photos_survives_ai_db_failure(admin_client, monkeypatch):
    """ai.db(photo_tags) 조회가 실패해도(예: 잠김·손상) 공유 앨범 조회 자체는
    500이 아니라 200으로 응답해야 한다 — 태그만 빠지고 나머지는 정상 동작
    (CLIP 태깅 실패가 얼굴 스캔을 막지 않는 best-effort 원칙과 동일)."""
    from backend.routers import share as share_module

    async def _boom(*args, **kwargs):
        raise RuntimeError("ai.db unavailable")

    monkeypatch.setattr(share_module, "load_photo_tags", _boom)

    token = await _setup_link(admin_client, with_photos=True)
    await _auth(admin_client, token)

    r = await admin_client.get(f"/api/share/{token}/photos")
    assert r.status_code == 200
    photos = r.json()["photos"]
    assert len(photos) == 2
    assert all(p["ai_tags"] == [] for p in photos)


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


# ── photos 페이지네이션 ────────────────────────────────────────────────────────

async def test_photos_pagination_first_page(admin_client):
    token = await _setup_link(admin_client, with_photos=True)
    await _auth(admin_client, token)
    data = (await admin_client.get(f"/api/share/{token}/photos?size=1")).json()
    assert data["total"] == 2
    assert len(data["photos"]) == 1
    assert data["page"] == 1


async def test_photos_pagination_second_page(admin_client):
    token = await _setup_link(admin_client, with_photos=True)
    await _auth(admin_client, token)
    data = (await admin_client.get(f"/api/share/{token}/photos?page=2&size=1")).json()
    assert data["total"] == 2
    assert len(data["photos"]) == 1
    assert data["page"] == 2


async def test_photos_size_zero_returns_all(admin_client):
    """size=0(기본값)이면 전체 반환."""
    token = await _setup_link(admin_client, with_photos=True)
    await _auth(admin_client, token)
    data = (await admin_client.get(f"/api/share/{token}/photos?size=0")).json()
    assert data["total"] == 2
    assert len(data["photos"]) == 2


# ── OG 이미지 ─────────────────────────────────────────────────────────────────

async def test_og_image_invalid_token(admin_client):
    r = await admin_client.get("/api/share/nonexistent/og-image")
    assert r.status_code == 404


async def test_og_image_empty_album(admin_client):
    token = await _setup_link(admin_client, with_photos=False)
    r = await admin_client.get(f"/api/share/{token}/og-image")
    assert r.status_code == 404


async def test_og_image_blocked_for_password_protected_album(admin_client, tmp_path):
    """패스워드 보호 앨범은 세션 없이 커버 이미지를 얻을 수 없어야 한다."""
    photos_dir = tmp_path / "photos"
    img_path = photos_dir / "cover.jpg"
    Image.new("RGB", (400, 300), color="blue").save(str(img_path))

    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "Protected OG", "photo_paths": ["cover.jpg"]},
    )
    album_id = r.json()["id"]
    r = await admin_client.post(
        f"/api/admin/albums/{album_id}/links", json={"password": "secret"}
    )
    token = r.json()["token"]

    r = await admin_client.get(f"/api/share/{token}/og-image")
    assert r.status_code == 404


async def test_og_image_with_photos(admin_client, tmp_path):
    photos_dir = tmp_path / "photos"
    img_path = photos_dir / "cover.jpg"
    Image.new("RGB", (400, 300), color="blue").save(str(img_path))

    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "OG Test", "photo_paths": ["cover.jpg"]},
    )
    album_id = r.json()["id"]
    r = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    token = r.json()["token"]

    r = await admin_client.get(f"/api/share/{token}/og-image")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"


# ── SPA OG 메타 태그 주입 ──────────────────────────────────────────────────────

async def test_share_spa_og_tags_injected(admin_client, monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://example.com")
    token = await _setup_link(admin_client)
    r = await admin_client.get(f"/s/{token}")
    assert r.status_code == 200
    assert 'property="og:title"' in r.text
    assert "Test Album" in r.text
    assert f"/api/share/{token}/og-image" in r.text
    assert f"/s/{token}" in r.text


async def test_share_spa_og_skips_image_without_base_url(admin_client, monkeypatch):
    monkeypatch.setenv("BASE_URL", "")
    token = await _setup_link(admin_client)
    r = await admin_client.get(f"/s/{token}")
    assert r.status_code == 200
    assert 'property="og:title"' in r.text
    assert 'property="og:image"' not in r.text


async def test_share_spa_og_skips_image_for_password_protected_album(admin_client, monkeypatch):
    """패스워드 보호 앨범은 제목/설명은 노출하되 og:image는 생략해야 한다."""
    monkeypatch.setenv("BASE_URL", "https://example.com")
    token = await _setup_link(admin_client, password="secret")
    r = await admin_client.get(f"/s/{token}")
    assert r.status_code == 200
    assert 'property="og:title"' in r.text
    assert "Test Album" in r.text
    assert 'property="og:image"' not in r.text
    assert f'property="og:url" content="https://example.com/s/{token}"' in r.text


async def test_share_spa_invalid_token_still_returns_html(admin_client):
    r = await admin_client.get("/s/nonexistent-token")
    # index.html 존재 시 200, 없으면 dict 반환
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        assert 'property="og:title"' not in r.text


# ── 브루트포스 잠금 (DB 기반) ─────────────────────────────────────────────────

async def test_brute_force_lockout_persists_across_requests(admin_client):
    """DB 기반 실패 기록이 요청 간 유지되어 잠금이 작동해야 한다."""
    token = await _setup_link(admin_client, password="secret")
    for _ in range(5):
        r = await _auth(admin_client, token, password="wrong")
        assert r.status_code == 401
    r = await _auth(admin_client, token, password="wrong")
    assert r.status_code == 429


async def test_brute_force_resets_on_correct_password(admin_client):
    """올바른 패스워드 입력 후 실패 카운터가 초기화된다."""
    token = await _setup_link(admin_client, password="secret")
    for _ in range(4):
        await _auth(admin_client, token, password="wrong")
    r = await _auth(admin_client, token, password="secret")
    assert r.status_code == 200
    # 카운터 리셋 후 재시도 가능
    r = await _auth(admin_client, token, password="wrong")
    assert r.status_code == 401  # 429가 아닌 401


async def test_lockout_is_per_ip_not_just_token(admin_client):
    """token 단독 키였다면 공격자의 5회 오입력이 다른 IP의 정상 사용자까지
    차단시켰을 것 — IP+token 복합 키로 공격자 IP만 잠긴다."""
    token = await _setup_link(admin_client, password="secret")

    from backend.main import app

    attacker_transport = ASGITransport(app=app, client=("9.9.9.9", 1234))
    async with AsyncClient(transport=attacker_transport, base_url="http://test") as attacker:
        for _ in range(5):
            r = await attacker.post(f"/api/share/{token}/auth", json={"password": "wrong"})
            assert r.status_code == 401
        r = await attacker.post(f"/api/share/{token}/auth", json={"password": "wrong"})
        assert r.status_code == 429

    # 다른 IP(기본 admin_client, 127.0.0.1)는 여전히 정상 인증 가능해야 한다
    r = await _auth(admin_client, token, password="secret")
    assert r.status_code == 200


# ── 공개 GET 엔드포인트 속도 제한 ─────────────────────────────────────────────

async def test_public_endpoint_rate_limit_ignores_valid_token_lookups(admin_client):
    """정상 토큰 조회(200)는 아무리 반복해도 잠금에 영향을 주지 않는다 —
    프론트엔드가 진입 시마다 호출하는 정상 트래픽을 오탐하지 않기 위함."""
    token = await _setup_link(admin_client)
    for _ in range(40):
        r = await admin_client.get(f"/api/share/{token}")
        assert r.status_code == 200


async def test_public_endpoint_rate_limit_blocks_invalid_token_probing(admin_client):
    """존재하지 않는 토큰(404) 반복 조회는 enumeration 시도로 간주해 IP당 60초 30회로 제한된다."""
    for _ in range(30):
        r = await admin_client.get("/api/share/nonexistent-token")
        assert r.status_code == 404
    r = await admin_client.get("/api/share/nonexistent-token")
    assert r.status_code == 429


# ── PHOTO_ROOT 이탈 경로 차단 ─────────────────────────────────────────────────

async def test_og_image_blocks_path_outside_photo_root(admin_client):
    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "Escape Album", "photo_paths": ["../outside.jpg"]},
    )
    album_id = r.json()["id"]
    r = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    token = r.json()["token"]

    r = await admin_client.get(f"/api/share/{token}/og-image")
    assert r.status_code == 403


async def test_download_zip_blocks_path_outside_photo_root(admin_client):
    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "Escape Album 2", "photo_paths": ["../outside2.jpg"]},
    )
    album_id = r.json()["id"]
    r = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    token = r.json()["token"]
    await _auth(admin_client, token)

    r = await admin_client.get(f"/api/share/{token}/download")
    assert r.status_code == 403
