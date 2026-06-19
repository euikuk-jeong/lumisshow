import pytest


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

async def _make_album(client, name="Album"):
    r = await client.post("/api/admin/albums", json={"name": name})
    assert r.status_code == 201
    return r.json()["id"]


# ── 목록 & 생성 ───────────────────────────────────────────────────────────────

async def test_list_links_empty(admin_client):
    album_id = await _make_album(admin_client)
    r = await admin_client.get(f"/api/admin/albums/{album_id}/links")
    assert r.status_code == 200
    assert r.json() == []


async def test_create_link_minimal(admin_client):
    album_id = await _make_album(admin_client)
    r = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    assert r.status_code == 201
    data = r.json()
    assert "token" in data
    assert len(data["token"]) == 10
    assert data["has_password"] is False
    assert data["is_active"] is True
    assert data["expires_at"] is None
    assert "/s/" in data["share_url"]


async def test_create_link_with_password(admin_client):
    album_id = await _make_album(admin_client)
    r = await admin_client.post(
        f"/api/admin/albums/{album_id}/links",
        json={"password": "secret123"},
    )
    assert r.status_code == 201
    assert r.json()["has_password"] is True


async def test_create_link_with_expiry(admin_client):
    album_id = await _make_album(admin_client)
    r = await admin_client.post(
        f"/api/admin/albums/{album_id}/links",
        json={"expires_at": "2099-12-31T00:00:00"},
    )
    assert r.status_code == 201
    assert r.json()["expires_at"] is not None


async def test_create_multiple_links(admin_client):
    album_id = await _make_album(admin_client)
    await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    r = await admin_client.get(f"/api/admin/albums/{album_id}/links")
    assert len(r.json()) == 2


async def test_links_are_unique_tokens(admin_client):
    album_id = await _make_album(admin_client)
    r1 = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    r2 = await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    assert r1.json()["token"] != r2.json()["token"]


async def test_create_link_album_not_found(admin_client):
    r = await admin_client.post("/api/admin/albums/9999/links", json={})
    assert r.status_code == 404


async def test_list_links_album_not_found(admin_client):
    r = await admin_client.get("/api/admin/albums/9999/links")
    assert r.status_code == 404


# ── 수정 ──────────────────────────────────────────────────────────────────────

async def test_update_link_deactivate(admin_client):
    album_id = await _make_album(admin_client)
    link = (await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})).json()
    r = await admin_client.patch(
        f"/api/admin/albums/{album_id}/links/{link['id']}",
        json={"is_active": False},
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is False


async def test_update_link_set_password(admin_client):
    album_id = await _make_album(admin_client)
    link = (await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})).json()
    r = await admin_client.patch(
        f"/api/admin/albums/{album_id}/links/{link['id']}",
        json={"password": "newpass"},
    )
    assert r.status_code == 200
    assert r.json()["has_password"] is True


async def test_update_link_clear_password(admin_client):
    album_id = await _make_album(admin_client)
    link = (
        await admin_client.post(
            f"/api/admin/albums/{album_id}/links", json={"password": "old"}
        )
    ).json()
    r = await admin_client.patch(
        f"/api/admin/albums/{album_id}/links/{link['id']}",
        json={"password": None},
    )
    assert r.status_code == 200
    assert r.json()["has_password"] is False


async def test_update_link_not_found(admin_client):
    album_id = await _make_album(admin_client)
    r = await admin_client.patch(
        f"/api/admin/albums/{album_id}/links/9999",
        json={"is_active": False},
    )
    assert r.status_code == 404


async def test_update_link_wrong_album(admin_client):
    album1 = await _make_album(admin_client, "A1")
    album2 = await _make_album(admin_client, "A2")
    link = (await admin_client.post(f"/api/admin/albums/{album1}/links", json={})).json()
    # album2로 album1의 링크를 수정 시도
    r = await admin_client.patch(
        f"/api/admin/albums/{album2}/links/{link['id']}",
        json={"is_active": False},
    )
    assert r.status_code == 404


# ── 삭제 ──────────────────────────────────────────────────────────────────────

async def test_delete_link(admin_client):
    album_id = await _make_album(admin_client)
    link = (await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})).json()
    r = await admin_client.delete(f"/api/admin/albums/{album_id}/links/{link['id']}")
    assert r.status_code == 204
    links = (await admin_client.get(f"/api/admin/albums/{album_id}/links")).json()
    assert links == []


async def test_delete_link_not_found(admin_client):
    album_id = await _make_album(admin_client)
    r = await admin_client.delete(f"/api/admin/albums/{album_id}/links/9999")
    assert r.status_code == 404


async def test_album_delete_cascades_links(admin_client):
    album_id = await _make_album(admin_client)
    await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    await admin_client.delete(f"/api/admin/albums/{album_id}")
    # 앨범 삭제 시 링크도 사라져야 함 (cascade)
    r = await admin_client.get(f"/api/admin/albums/{album_id}/links")
    assert r.status_code == 404


# ── 인증 필요 ─────────────────────────────────────────────────────────────────

async def test_list_links_requires_auth(client):
    r = await client.get("/api/admin/albums/1/links")
    assert r.status_code == 401


async def test_create_link_requires_auth(client):
    r = await client.post("/api/admin/albums/1/links", json={})
    assert r.status_code == 401
