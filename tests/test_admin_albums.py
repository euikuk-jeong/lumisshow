import os

import pytest


# ── 목록 & 생성 ───────────────────────────────────────────────────────────────

async def test_list_albums_empty(admin_client):
    r = await admin_client.get("/api/admin/albums")
    assert r.status_code == 200
    assert r.json() == []


async def test_create_album_minimal(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "My Album"})
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "My Album"
    assert data["photo_count"] == 0
    assert "id" in data


async def test_create_album_with_description(admin_client):
    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "Desc", "description": "A nice album"},
    )
    assert r.status_code == 201
    assert r.json()["description"] == "A nice album"


async def test_create_album_with_photos(admin_client):
    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "Trip", "photo_paths": ["a.jpg", "b.jpg"]},
    )
    assert r.status_code == 201
    assert r.json()["photo_count"] == 2


async def test_list_albums_returns_all(admin_client):
    await admin_client.post("/api/admin/albums", json={"name": "A1"})
    await admin_client.post("/api/admin/albums", json={"name": "A2"})
    r = await admin_client.get("/api/admin/albums")
    assert r.status_code == 200
    assert len(r.json()) == 2


# ── 상세 조회 ─────────────────────────────────────────────────────────────────

async def test_get_album_detail(admin_client):
    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "Detail", "photo_paths": ["x.jpg"]},
    )
    album_id = r.json()["id"]
    r = await admin_client.get(f"/api/admin/albums/{album_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "Detail"
    assert len(data["photos"]) == 1
    assert os.path.basename(data["photos"][0]["file_path"]) == "x.jpg"


async def test_get_album_photos_sorted_by_sort_order(admin_client):
    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "Sorted", "photo_paths": ["first.jpg", "second.jpg"]},
    )
    album_id = r.json()["id"]
    data = (await admin_client.get(f"/api/admin/albums/{album_id}")).json()
    assert os.path.basename(data["photos"][0]["file_path"]) == "first.jpg"
    assert os.path.basename(data["photos"][1]["file_path"]) == "second.jpg"


async def test_get_album_not_found(admin_client):
    r = await admin_client.get("/api/admin/albums/9999")
    assert r.status_code == 404


# ── 수정 ─────────────────────────────────────────────────────────────────────

async def test_update_album_name(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "Old"})
    album_id = r.json()["id"]
    r = await admin_client.patch(f"/api/admin/albums/{album_id}", json={"name": "New"})
    assert r.status_code == 200
    assert r.json()["name"] == "New"


async def test_update_album_cover_path(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "Cover"})
    album_id = r.json()["id"]
    r = await admin_client.patch(
        f"/api/admin/albums/{album_id}", json={"cover_path": "cover.jpg"}
    )
    assert r.status_code == 200
    assert r.json()["cover_path"] == "cover.jpg"


async def test_update_album_empty_body_is_noop(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "Stable"})
    album_id = r.json()["id"]
    r = await admin_client.patch(f"/api/admin/albums/{album_id}", json={})
    assert r.status_code == 200
    assert r.json()["name"] == "Stable"


async def test_update_album_not_found(admin_client):
    r = await admin_client.patch("/api/admin/albums/9999", json={"name": "X"})
    assert r.status_code == 404


# ── 삭제 ─────────────────────────────────────────────────────────────────────

async def test_delete_album(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "Del"})
    album_id = r.json()["id"]
    assert (await admin_client.delete(f"/api/admin/albums/{album_id}")).status_code == 204
    assert (await admin_client.get(f"/api/admin/albums/{album_id}")).status_code == 404


async def test_delete_album_cascades_photos(admin_client):
    r = await admin_client.post(
        "/api/admin/albums", json={"name": "Cascade", "photo_paths": ["p.jpg"]}
    )
    album_id = r.json()["id"]
    await admin_client.delete(f"/api/admin/albums/{album_id}")
    # 앨범 삭제 후 목록이 비어있어야 함
    r = await admin_client.get("/api/admin/albums")
    assert r.json() == []


async def test_delete_album_not_found(admin_client):
    r = await admin_client.delete("/api/admin/albums/9999")
    assert r.status_code == 404


# ── 사진 추가 ─────────────────────────────────────────────────────────────────

async def test_add_photos(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "A"})
    album_id = r.json()["id"]
    r = await admin_client.post(
        f"/api/admin/albums/{album_id}/photos",
        json={"photo_paths": ["c.jpg", "d.jpg"]},
    )
    assert r.status_code == 204
    data = (await admin_client.get(f"/api/admin/albums/{album_id}")).json()
    assert data["photo_count"] == 2


async def test_add_photos_deduplication(admin_client):
    r = await admin_client.post(
        "/api/admin/albums", json={"name": "Dup", "photo_paths": ["e.jpg"]}
    )
    album_id = r.json()["id"]
    await admin_client.post(
        f"/api/admin/albums/{album_id}/photos",
        json={"photo_paths": ["e.jpg"]},
    )
    data = (await admin_client.get(f"/api/admin/albums/{album_id}")).json()
    assert data["photo_count"] == 1


async def test_add_photos_appends_sort_order(admin_client):
    r = await admin_client.post(
        "/api/admin/albums", json={"name": "Ord", "photo_paths": ["first.jpg"]}
    )
    album_id = r.json()["id"]
    await admin_client.post(
        f"/api/admin/albums/{album_id}/photos",
        json={"photo_paths": ["second.jpg"]},
    )
    photos = (await admin_client.get(f"/api/admin/albums/{album_id}")).json()["photos"]
    assert os.path.basename(photos[0]["file_path"]) == "first.jpg"
    assert os.path.basename(photos[1]["file_path"]) == "second.jpg"


async def test_add_photos_to_nonexistent_album(admin_client):
    r = await admin_client.post(
        "/api/admin/albums/9999/photos",
        json={"photo_paths": ["x.jpg"]},
    )
    assert r.status_code == 404


# ── 사진 제거 ─────────────────────────────────────────────────────────────────

async def test_remove_photos(admin_client):
    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "R", "photo_paths": ["f.jpg", "g.jpg"]},
    )
    album_id = r.json()["id"]
    r = await admin_client.request(
        "DELETE",
        f"/api/admin/albums/{album_id}/photos",
        json={"photo_paths": ["f.jpg"]},
    )
    assert r.status_code == 204
    data = (await admin_client.get(f"/api/admin/albums/{album_id}")).json()
    assert data["photo_count"] == 1
    assert os.path.basename(data["photos"][0]["file_path"]) == "g.jpg"


async def test_remove_nonexistent_photo_is_noop(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "Noop"})
    album_id = r.json()["id"]
    r = await admin_client.request(
        "DELETE",
        f"/api/admin/albums/{album_id}/photos",
        json={"photo_paths": ["no_such.jpg"]},
    )
    assert r.status_code == 204


# ── 순서 변경 ─────────────────────────────────────────────────────────────────

async def test_reorder_photos(admin_client):
    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "Reorder", "photo_paths": ["h.jpg", "i.jpg"]},
    )
    album_id = r.json()["id"]
    photos = (await admin_client.get(f"/api/admin/albums/{album_id}")).json()["photos"]

    new_orders = [
        {"id": photos[0]["id"], "sort_order": 10},
        {"id": photos[1]["id"], "sort_order": 0},
    ]
    r = await admin_client.put(
        f"/api/admin/albums/{album_id}/photos/order",
        json={"orders": new_orders},
    )
    assert r.status_code == 204

    photos_after = (await admin_client.get(f"/api/admin/albums/{album_id}")).json()["photos"]
    assert os.path.basename(photos_after[0]["file_path"]) == "i.jpg"
    assert os.path.basename(photos_after[1]["file_path"]) == "h.jpg"


# ── 인증 필요 ─────────────────────────────────────────────────────────────────

async def test_list_albums_requires_auth(client):
    r = await client.get("/api/admin/albums")
    assert r.status_code == 401


async def test_create_album_requires_auth(client):
    r = await client.post("/api/admin/albums", json={"name": "X"})
    assert r.status_code == 401


async def test_delete_album_requires_auth(client):
    r = await client.delete("/api/admin/albums/1")
    assert r.status_code == 401
