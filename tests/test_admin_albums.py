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
    r = await admin_client.put(f"/api/admin/albums/{album_id}", json={"name": "New"})
    assert r.status_code == 200
    assert r.json()["name"] == "New"


async def test_update_album_cover_path(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "Cover"})
    album_id = r.json()["id"]
    r = await admin_client.put(
        f"/api/admin/albums/{album_id}", json={"cover_path": "cover.jpg"}
    )
    assert r.status_code == 200
    assert r.json()["cover_path"] == "cover.jpg"


async def test_update_album_empty_body_is_noop(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "Stable"})
    album_id = r.json()["id"]
    r = await admin_client.put(f"/api/admin/albums/{album_id}", json={})
    assert r.status_code == 200
    assert r.json()["name"] == "Stable"


async def test_update_album_not_found(admin_client):
    r = await admin_client.put("/api/admin/albums/9999", json={"name": "X"})
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


# ── 사진 정렬 ─────────────────────────────────────────────────────────────────

async def test_photo_sort_defaults_taken_at_asc(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "Sort"})
    data = r.json()
    assert data["photo_sort_by"] == "taken_at"
    assert data["photo_sort_dir"] == "asc"


async def test_photo_sort_filename_asc(admin_client):
    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "S", "photo_paths": ["zebra.jpg", "apple.jpg", "mango.jpg"]},
    )
    album_id = r.json()["id"]
    await admin_client.put(
        f"/api/admin/albums/{album_id}",
        json={"photo_sort_by": "filename", "photo_sort_dir": "asc"},
    )
    photos = (await admin_client.get(f"/api/admin/albums/{album_id}")).json()["photos"]
    names = [os.path.basename(p["file_path"]) for p in photos]
    assert names == ["apple.jpg", "mango.jpg", "zebra.jpg"]


async def test_photo_sort_filename_desc(admin_client):
    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "S", "photo_paths": ["apple.jpg", "zebra.jpg", "mango.jpg"]},
    )
    album_id = r.json()["id"]
    await admin_client.put(
        f"/api/admin/albums/{album_id}",
        json={"photo_sort_by": "filename", "photo_sort_dir": "desc"},
    )
    photos = (await admin_client.get(f"/api/admin/albums/{album_id}")).json()["photos"]
    names = [os.path.basename(p["file_path"]) for p in photos]
    assert names == ["zebra.jpg", "mango.jpg", "apple.jpg"]


async def test_photo_sort_taken_at_none_falls_back_to_filename(admin_client):
    # 파일이 없으면 taken_at=None → 파일명 tiebreak으로 정렬
    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "S", "photo_paths": ["charlie.jpg", "alpha.jpg", "bravo.jpg"]},
    )
    album_id = r.json()["id"]
    await admin_client.put(
        f"/api/admin/albums/{album_id}",
        json={"photo_sort_by": "taken_at", "photo_sort_dir": "asc"},
    )
    photos = (await admin_client.get(f"/api/admin/albums/{album_id}")).json()["photos"]
    names = [os.path.basename(p["file_path"]) for p in photos]
    assert names == ["alpha.jpg", "bravo.jpg", "charlie.jpg"]


async def test_add_photos_respects_sort(admin_client):
    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "S", "photo_paths": ["z.jpg"]},
    )
    album_id = r.json()["id"]
    await admin_client.post(
        f"/api/admin/albums/{album_id}/photos",
        json={"photo_paths": ["a.jpg", "m.jpg"]},
    )
    photos = (await admin_client.get(f"/api/admin/albums/{album_id}")).json()["photos"]
    names = [os.path.basename(p["file_path"]) for p in photos]
    assert names == ["a.jpg", "m.jpg", "z.jpg"]


async def test_photo_sort_invalid_values_sanitized(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "S"})
    album_id = r.json()["id"]
    r = await admin_client.put(
        f"/api/admin/albums/{album_id}",
        json={"photo_sort_by": "badvalue", "photo_sort_dir": "baddir"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["photo_sort_by"] == "filename"
    assert data["photo_sort_dir"] == "asc"


# ── 복제 ─────────────────────────────────────────────────────────────────────

async def test_duplicate_album_basic(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "Original"})
    album_id = r.json()["id"]

    r = await admin_client.post(
        f"/api/admin/albums/{album_id}/duplicate",
        json={"name": "Copy"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Copy"
    assert data["id"] != album_id


async def test_duplicate_album_copies_photos(admin_client):
    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "Src", "photo_paths": ["a.jpg", "b.jpg"]},
    )
    album_id = r.json()["id"]

    r = await admin_client.post(
        f"/api/admin/albums/{album_id}/duplicate",
        json={"name": "Dup"},
    )
    new_id = r.json()["id"]

    r = await admin_client.get(f"/api/admin/albums/{new_id}")
    assert r.json()["photo_count"] == 2


async def test_duplicate_album_copies_slideshow_settings(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "Src"})
    album_id = r.json()["id"]
    await admin_client.put(
        f"/api/admin/albums/{album_id}",
        json={"slideshow_interval": 12, "slideshow_order": "random"},
    )

    r = await admin_client.post(
        f"/api/admin/albums/{album_id}/duplicate",
        json={"name": "Dup"},
    )
    data = r.json()
    assert data["slideshow_interval"] == 12
    assert data["slideshow_order"] == "random"


async def test_duplicate_album_description_copied(admin_client):
    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "Src", "description": "A nice description"},
    )
    album_id = r.json()["id"]

    r = await admin_client.post(
        f"/api/admin/albums/{album_id}/duplicate",
        json={"name": "Dup"},
    )
    assert r.json()["description"] == "A nice description"


async def test_duplicate_album_not_found(admin_client):
    r = await admin_client.post(
        "/api/admin/albums/999/duplicate",
        json={"name": "X"},
    )
    assert r.status_code == 404


async def test_duplicate_album_requires_auth(client):
    r = await client.post("/api/admin/albums/1/duplicate", json={"name": "X"})
    assert r.status_code == 401


# ── 조회수 리셋 ────────────────────────────────────────────────────────────────

async def test_reset_view_count(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "A"})
    album_id = r.json()["id"]
    # view_count를 직접 올릴 DB 접근 대신, 초기값 0임을 확인 후 리셋 호출
    r = await admin_client.delete(f"/api/admin/albums/{album_id}/view-count")
    assert r.status_code == 204

    r = await admin_client.get(f"/api/admin/albums/{album_id}")
    assert r.json()["view_count"] == 0


async def test_reset_view_count_not_found(admin_client):
    r = await admin_client.delete("/api/admin/albums/999/view-count")
    assert r.status_code == 404


async def test_reset_view_count_requires_auth(client):
    r = await client.delete("/api/admin/albums/1/view-count")
    assert r.status_code == 401


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
