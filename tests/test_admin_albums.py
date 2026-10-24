import os
import time

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image


# ── 목록 & 생성 ───────────────────────────────────────────────────────────────

async def test_list_albums_empty(admin_client):
    r = await admin_client.get("/api/admin/albums")
    assert r.status_code == 200
    assert r.json()["items"] == []


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


async def test_album_next_expires_at(admin_client):
    album_id = (await admin_client.post("/api/admin/albums", json={"name": "Expiry"})).json()["id"]
    r = await admin_client.get("/api/admin/albums")
    assert r.json()["items"][0]["next_expires_at"] is None

    # 만료일 없는 링크만 있으면 여전히 None
    await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    r = await admin_client.get(f"/api/admin/albums/{album_id}")
    assert r.json()["next_expires_at"] is None

    # 만료일 있는 링크가 생기면 그 값을 반환
    await admin_client.post(
        f"/api/admin/albums/{album_id}/links", json={"expires_at": "2099-12-31T00:00:00"},
    )
    r = await admin_client.get("/api/admin/albums")
    assert r.json()["items"][0]["next_expires_at"] is not None

    # 이미 지난 만료일은 후보에서 제외 (활성 링크 취급 안 함)
    await admin_client.post(
        f"/api/admin/albums/{album_id}/links", json={"expires_at": "2000-01-01T00:00:00"},
    )
    r = await admin_client.get(f"/api/admin/albums/{album_id}")
    assert r.json()["next_expires_at"].startswith("2099")


async def test_album_active_link_count(admin_client):
    album_id = (await admin_client.post("/api/admin/albums", json={"name": "Links"})).json()["id"]
    r = await admin_client.get("/api/admin/albums")
    assert r.json()["items"][0]["active_link_count"] == 0

    await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    link2 = (
        await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    ).json()
    r = await admin_client.get("/api/admin/albums")
    assert r.json()["items"][0]["active_link_count"] == 2

    # 비활성 링크는 카운트에서 제외
    await admin_client.patch(
        f"/api/admin/albums/{album_id}/links/{link2['id']}",
        json={"is_active": False},
    )
    r = await admin_client.get(f"/api/admin/albums/{album_id}")
    assert r.json()["active_link_count"] == 1

    # 만료된 링크도 카운트에서 제외
    await admin_client.patch(
        f"/api/admin/albums/{album_id}/links/{link2['id']}",
        json={"is_active": True, "expires_at": "2000-01-01T00:00:00"},
    )
    r = await admin_client.get(f"/api/admin/albums/{album_id}")
    assert r.json()["active_link_count"] == 1


async def test_list_albums_returns_all(admin_client):
    await admin_client.post("/api/admin/albums", json={"name": "A1"})
    await admin_client.post("/api/admin/albums", json={"name": "A2"})
    r = await admin_client.get("/api/admin/albums")
    assert r.status_code == 200
    assert len(r.json()["items"]) == 2


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


async def test_create_album_title_font_defaults_null(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "FontDefault"})
    assert r.json()["title_font"] is None


async def test_update_album_title_font_round_trip(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "Font"})
    album_id = r.json()["id"]
    r = await admin_client.put(
        f"/api/admin/albums/{album_id}", json={"title_font": "gowun-batang"}
    )
    assert r.status_code == 200
    assert r.json()["title_font"] == "gowun-batang"

    r = await admin_client.get(f"/api/admin/albums/{album_id}")
    assert r.json()["title_font"] == "gowun-batang"

    # null로 되돌리면 시스템 기본으로 복귀
    r = await admin_client.put(f"/api/admin/albums/{album_id}", json={"title_font": None})
    assert r.status_code == 200
    assert r.json()["title_font"] is None


async def test_update_album_title_font_invalid_rejected(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "FontInvalid"})
    album_id = r.json()["id"]
    r = await admin_client.put(
        f"/api/admin/albums/{album_id}", json={"title_font": "comic-sans"}
    )
    assert r.status_code == 422


async def test_create_album_cover_position_defaults_auto(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "CoverPosDefault"})
    assert r.json()["cover_position"] == "auto"


@pytest.mark.parametrize("position", ["auto", "top", "center", "bottom"])
async def test_update_album_cover_position_round_trip(admin_client, position):
    r = await admin_client.post("/api/admin/albums", json={"name": "CoverPos"})
    album_id = r.json()["id"]
    r = await admin_client.put(
        f"/api/admin/albums/{album_id}", json={"cover_position": position}
    )
    assert r.status_code == 200
    assert r.json()["cover_position"] == position

    r = await admin_client.get(f"/api/admin/albums/{album_id}")
    assert r.json()["cover_position"] == position


async def test_update_album_cover_position_null_reads_auto(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "CoverPosNull"})
    album_id = r.json()["id"]
    await admin_client.put(f"/api/admin/albums/{album_id}", json={"cover_position": "bottom"})
    r = await admin_client.put(f"/api/admin/albums/{album_id}", json={"cover_position": None})
    assert r.status_code == 200
    assert r.json()["cover_position"] == "auto"


async def test_update_album_cover_position_invalid_rejected(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "CoverPosInvalid"})
    album_id = r.json()["id"]
    r = await admin_client.put(
        f"/api/admin/albums/{album_id}", json={"cover_position": "left"}
    )
    assert r.status_code == 422


async def test_update_album_cover_position_requires_auth(client):
    r = await client.put("/api/admin/albums/1", json={"cover_position": "top"})
    assert r.status_code == 401


async def test_create_album_show_all_tags_defaults_false(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "TagsDefault"})
    assert r.json()["show_all_tags"] is False


async def test_update_album_show_all_tags_round_trip(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "Tags"})
    album_id = r.json()["id"]
    r = await admin_client.put(
        f"/api/admin/albums/{album_id}", json={"show_all_tags": True}
    )
    assert r.status_code == 200
    assert r.json()["show_all_tags"] is True

    r = await admin_client.get(f"/api/admin/albums/{album_id}")
    assert r.json()["show_all_tags"] is True

    r = await admin_client.put(
        f"/api/admin/albums/{album_id}", json={"show_all_tags": False}
    )
    assert r.status_code == 200
    assert r.json()["show_all_tags"] is False


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
    assert r.json()["items"] == []


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
    assert r.status_code == 200
    body = r.json()
    assert body["added"] == 2
    assert body["skipped"] == 0
    data = (await admin_client.get(f"/api/admin/albums/{album_id}")).json()
    assert data["photo_count"] == 2


async def test_add_photos_deduplication(admin_client):
    r = await admin_client.post(
        "/api/admin/albums", json={"name": "Dup", "photo_paths": ["e.jpg"]}
    )
    album_id = r.json()["id"]
    r = await admin_client.post(
        f"/api/admin/albums/{album_id}/photos",
        json={"photo_paths": ["e.jpg"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["added"] == 0
    assert body["skipped"] == 1
    data = (await admin_client.get(f"/api/admin/albums/{album_id}")).json()
    assert data["photo_count"] == 1


async def test_add_photos_empty_paths(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "Empty"})
    album_id = r.json()["id"]
    r = await admin_client.post(
        f"/api/admin/albums/{album_id}/photos",
        json={"photo_paths": []},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["added"] == 0
    assert body["skipped"] == 0


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


async def test_duplicate_album_copies_title_font(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "Src"})
    album_id = r.json()["id"]
    await admin_client.put(f"/api/admin/albums/{album_id}", json={"title_font": "jua"})

    r = await admin_client.post(
        f"/api/admin/albums/{album_id}/duplicate",
        json={"name": "Dup"},
    )
    assert r.json()["title_font"] == "jua"


async def test_duplicate_album_copies_cover_position(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "SrcCoverPos"})
    album_id = r.json()["id"]
    await admin_client.put(f"/api/admin/albums/{album_id}", json={"cover_position": "center"})

    r = await admin_client.post(
        f"/api/admin/albums/{album_id}/duplicate",
        json={"name": "DupCoverPos"},
    )
    assert r.json()["cover_position"] == "center"


async def test_duplicate_album_copies_show_all_tags(admin_client):
    r = await admin_client.post("/api/admin/albums", json={"name": "SrcTags"})
    album_id = r.json()["id"]
    await admin_client.put(f"/api/admin/albums/{album_id}", json={"show_all_tags": True})

    r = await admin_client.post(
        f"/api/admin/albums/{album_id}/duplicate",
        json={"name": "DupTags"},
    )
    assert r.json()["show_all_tags"] is True


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


# ── taken_at 정렬 EXIF 검증 ──────────────────────────────────────────────────

def _make_jpg_with_exif(path, taken_at_str: str):
    """DateTime(IFD0/306) EXIF가 포함된 JPEG 생성."""
    img = Image.new("RGB", (100, 100))
    exif = img.getexif()
    exif[306] = taken_at_str
    img.save(str(path), "JPEG", exif=exif.tobytes())


@pytest_asyncio.fixture
async def dated_admin_client(tmp_path, monkeypatch):
    """EXIF 촬영일이 다른 사진 3장이 세팅된 admin_client."""
    photo_root = tmp_path / "photos"
    photo_root.mkdir()
    _make_jpg_with_exif(photo_root / "old.jpg",  "2022:01:15 08:00:00")
    _make_jpg_with_exif(photo_root / "new.jpg",  "2023:06:01 10:00:00")
    _make_jpg_with_exif(photo_root / "mid.jpg",  "2022:12:31 23:00:00")

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

    from backend.models.database import close_db_pool
    await close_db_pool()


async def test_photo_sort_taken_at_uses_exif(dated_admin_client):
    """taken_at 오름차순 정렬이 EXIF 날짜 순서를 따라야 한다."""
    r = await dated_admin_client.post(
        "/api/admin/albums",
        json={"name": "Dated", "photo_paths": ["new.jpg", "old.jpg", "mid.jpg"]},
    )
    assert r.status_code == 201
    album_id = r.json()["id"]

    await dated_admin_client.put(
        f"/api/admin/albums/{album_id}",
        json={"photo_sort_by": "taken_at", "photo_sort_dir": "asc"},
    )

    photos = (await dated_admin_client.get(f"/api/admin/albums/{album_id}")).json()["photos"]
    names = [os.path.basename(p["file_path"]) for p in photos]
    assert names == ["old.jpg", "mid.jpg", "new.jpg"], f"EXIF 날짜 오름차순 정렬 실패: {names}"


async def test_get_album_photos_include_taken_at(dated_admin_client):
    """앨범 상세 조회 시 각 사진에 EXIF taken_at이 포함되어야 한다 (날짜별 보기용)."""
    r = await dated_admin_client.post(
        "/api/admin/albums",
        json={"name": "WithDates", "photo_paths": ["old.jpg"]},
    )
    album_id = r.json()["id"]

    photos = (await dated_admin_client.get(f"/api/admin/albums/{album_id}")).json()["photos"]
    assert photos[0]["taken_at"] is not None
    assert photos[0]["taken_at"].startswith("2022-01-15")


async def test_get_album_photos_taken_at_none_without_exif(admin_client):
    """EXIF 없는 사진은 taken_at이 null로 응답되어야 한다."""
    r = await admin_client.post(
        "/api/admin/albums",
        json={"name": "NoExif", "photo_paths": ["nofile.jpg"]},
    )
    album_id = r.json()["id"]

    photos = (await admin_client.get(f"/api/admin/albums/{album_id}")).json()["photos"]
    assert photos[0]["taken_at"] is None


async def test_photo_sort_taken_at_uses_meta_cache(dated_admin_client, tmp_path):
    """정렬이 photo_meta_cache를 사용해야 한다 — 원본 파일 삭제 후에도 캐시 히트로 동일 정렬."""
    r = await dated_admin_client.post(
        "/api/admin/albums",
        json={"name": "Cached", "photo_paths": ["new.jpg", "old.jpg", "mid.jpg"]},
    )
    album_id = r.json()["id"]

    # 첫 정렬 — 캐시 미스 → EXIF 읽어 photo_meta_cache에 저장됨 (앨범 생성 시 기본 taken_at 정렬)
    photo_root = tmp_path / "photos"
    for name in ("new.jpg", "old.jpg", "mid.jpg"):
        (photo_root / name).unlink()

    # 파일이 사라져도 캐시에서 EXIF를 읽어 정렬돼야 한다
    await dated_admin_client.put(
        f"/api/admin/albums/{album_id}",
        json={"photo_sort_by": "taken_at", "photo_sort_dir": "desc"},
    )
    photos = (await dated_admin_client.get(f"/api/admin/albums/{album_id}")).json()["photos"]
    names = [os.path.basename(p["file_path"]) for p in photos]
    assert names == ["new.jpg", "mid.jpg", "old.jpg"], f"캐시 기반 정렬 실패: {names}"


async def test_photo_meta_cache_self_heals_when_file_mtime_changes(dated_admin_client, tmp_path):
    """캐시된 파일의 EXIF가 외부 앱 등으로 바뀌면(mtime도 함께 변함) 다음 조회 시
    캐시를 그대로 믿지 않고 다시 읽어야 한다."""
    r = await dated_admin_client.post(
        "/api/admin/albums",
        json={"name": "Refresh", "photo_paths": ["old.jpg"]},
    )
    album_id = r.json()["id"]

    # 첫 조회 — 캐시 미스 → EXIF 읽어 photo_meta_cache에 저장(2022-01-15)
    photos = (await dated_admin_client.get(f"/api/admin/albums/{album_id}")).json()["photos"]
    assert photos[0]["taken_at"].startswith("2022-01-15")

    # 외부 앱으로 EXIF를 고쳤다고 가정 — 파일을 새로 써서 mtime도 함께 바뀜
    # (파일시스템 mtime 해상도에 좌우되지 않도록 명시적으로 미래 시각으로 설정)
    photo_root = tmp_path / "photos"
    photo_path = photo_root / "old.jpg"
    _make_jpg_with_exif(photo_path, "2025:01:11 09:00:00")
    future = time.time() + 100
    os.utime(photo_path, (future, future))

    photos = (await dated_admin_client.get(f"/api/admin/albums/{album_id}")).json()["photos"]
    assert photos[0]["taken_at"].startswith("2025-01-11"), \
        f"mtime 변경을 감지하지 못해 캐시된 옛 날짜를 그대로 반환함: {photos[0]['taken_at']}"


async def test_photo_sort_taken_at_desc_uses_exif(dated_admin_client):
    """taken_at 내림차순 정렬이 EXIF 날짜 역순이어야 한다."""
    r = await dated_admin_client.post(
        "/api/admin/albums",
        json={"name": "Dated Desc", "photo_paths": ["new.jpg", "old.jpg", "mid.jpg"]},
    )
    album_id = r.json()["id"]

    await dated_admin_client.put(
        f"/api/admin/albums/{album_id}",
        json={"photo_sort_by": "taken_at", "photo_sort_dir": "desc"},
    )

    photos = (await dated_admin_client.get(f"/api/admin/albums/{album_id}")).json()["photos"]
    names = [os.path.basename(p["file_path"]) for p in photos]
    assert names == ["new.jpg", "mid.jpg", "old.jpg"], f"EXIF 날짜 내림차순 정렬 실패: {names}"



# ── 목록 검색 · 날짜 필터 · 페이징 ─────────────────────────────────────────────

async def _make_album(admin_client, name, created_at, description=None):
    """앨범 생성 후 created_at(UTC, SQLite 형식)을 직접 지정."""
    import aiosqlite
    from backend.models.database import _db_path

    body = {"name": name}
    if description is not None:
        body["description"] = description
    album_id = (await admin_client.post("/api/admin/albums", json=body)).json()["id"]
    async with aiosqlite.connect(_db_path()) as db:
        await db.execute("UPDATE albums SET created_at = ? WHERE id = ?", (created_at, album_id))
        await db.commit()
    return album_id


async def _set_tz(admin_client, offset_minutes):
    r = await admin_client.patch(
        "/api/admin/settings",
        json={"timezone_offset": offset_minutes, "timezone_label": f"UTC{offset_minutes:+d}m"},
    )
    assert r.status_code == 200


def _names(r):
    return [a["name"] for a in r.json()["items"]]


async def test_list_albums_envelope_defaults(admin_client):
    await _make_album(admin_client, "A", "2026-01-01 00:00:00")
    data = (await admin_client.get("/api/admin/albums")).json()
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["size"] == 24
    assert data["timezone_offset"] == 0


async def test_list_albums_search_name_and_description(admin_client):
    await _make_album(admin_client, "제주 여행", "2026-01-01 00:00:00")
    await _make_album(admin_client, "Birthday", "2026-01-02 00:00:00", description="제주에서 생일")
    await _make_album(admin_client, "Other", "2026-01-03 00:00:00", description="nothing")
    r = await admin_client.get("/api/admin/albums", params={"q": "제주"})
    assert sorted(_names(r)) == ["Birthday", "제주 여행"]
    assert r.json()["total"] == 2


async def test_list_albums_search_case_insensitive_and_trimmed(admin_client):
    await _make_album(admin_client, "Summer Trip", "2026-01-01 00:00:00")
    r = await admin_client.get("/api/admin/albums", params={"q": "  summer "})
    assert _names(r) == ["Summer Trip"]


async def test_list_albums_search_escapes_like_wildcards(admin_client):
    await _make_album(admin_client, "plain", "2026-01-01 00:00:00")
    await _make_album(admin_client, "100%_done", "2026-01-02 00:00:00")
    assert _names(await admin_client.get("/api/admin/albums", params={"q": "_"})) == ["100%_done"]
    assert _names(await admin_client.get("/api/admin/albums", params={"q": "%"})) == ["100%_done"]


async def test_list_albums_blank_query_returns_all(admin_client):
    await _make_album(admin_client, "A", "2026-01-01 00:00:00")
    await _make_album(admin_client, "B", "2026-01-02 00:00:00")
    r = await admin_client.get("/api/admin/albums", params={"q": "   "})
    assert r.json()["total"] == 2


async def test_list_albums_date_range_inclusive_utc(admin_client):
    await _make_album(admin_client, "before", "2026-09-30 23:59:59")
    await _make_album(admin_client, "first", "2026-10-01 00:00:00")
    await _make_album(admin_client, "last", "2026-10-31 23:59:59")
    await _make_album(admin_client, "after", "2026-11-01 00:00:00")
    r = await admin_client.get(
        "/api/admin/albums", params={"date_from": "2026-10-01", "date_to": "2026-10-31"},
    )
    assert _names(r) == ["last", "first"]


async def test_list_albums_date_open_ended(admin_client):
    await _make_album(admin_client, "old", "2025-06-01 00:00:00")
    await _make_album(admin_client, "new", "2026-06-01 00:00:00")
    assert _names(await admin_client.get("/api/admin/albums", params={"date_from": "2026-01-01"})) == ["new"]
    assert _names(await admin_client.get("/api/admin/albums", params={"date_to": "2025-12-31"})) == ["old"]


async def test_list_albums_date_uses_server_timezone_positive(admin_client):
    await _set_tz(admin_client, 540)  # KST
    # UTC 9/30 15:00 = KST 10/1 00:00 → 10월
    await _make_album(admin_client, "kst-oct", "2026-09-30 15:00:00")
    # UTC 9/30 14:59:59 = KST 9/30 23:59:59 → 9월
    await _make_album(admin_client, "kst-sep", "2026-09-30 14:59:59")
    r = await admin_client.get(
        "/api/admin/albums", params={"date_from": "2026-10-01", "date_to": "2026-10-31"},
    )
    assert _names(r) == ["kst-oct"]
    assert r.json()["timezone_offset"] == 540


async def test_list_albums_date_uses_server_timezone_negative(admin_client):
    await _set_tz(admin_client, -300)  # UTC-5
    # UTC 11/1 04:00 = 10/31 23:00 (UTC-5) → 10월
    await _make_album(admin_client, "oct", "2026-11-01 04:00:00")
    await _make_album(admin_client, "nov", "2026-11-01 05:00:00")
    r = await admin_client.get(
        "/api/admin/albums", params={"date_from": "2026-10-01", "date_to": "2026-10-31"},
    )
    assert _names(r) == ["oct"]


async def test_list_albums_query_and_date_combined(admin_client):
    await _make_album(admin_client, "trip 2025", "2025-05-01 00:00:00")
    await _make_album(admin_client, "trip 2026", "2026-05-01 00:00:00")
    await _make_album(admin_client, "party 2026", "2026-05-02 00:00:00")
    r = await admin_client.get(
        "/api/admin/albums", params={"q": "trip", "date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    assert _names(r) == ["trip 2026"]


async def test_list_albums_pagination(admin_client):
    for i in range(5):
        await _make_album(admin_client, f"a{i}", f"2026-01-0{i + 1} 00:00:00")
    p1 = await admin_client.get("/api/admin/albums", params={"page": 1, "size": 2})
    p2 = await admin_client.get("/api/admin/albums", params={"page": 2, "size": 2})
    p3 = await admin_client.get("/api/admin/albums", params={"page": 3, "size": 2})
    assert _names(p1) == ["a4", "a3"]
    assert _names(p2) == ["a2", "a1"]
    assert _names(p3) == ["a0"]
    assert p1.json()["total"] == 5


async def test_list_albums_pagination_stable_for_same_created_at(admin_client):
    ids = [await _make_album(admin_client, f"s{i}", "2026-01-01 00:00:00") for i in range(3)]
    p1 = (await admin_client.get("/api/admin/albums", params={"size": 2})).json()["items"]
    p2 = (await admin_client.get("/api/admin/albums", params={"size": 2, "page": 2})).json()["items"]
    assert [a["id"] for a in p1 + p2] == sorted(ids, reverse=True)


async def test_list_albums_page_beyond_last_returns_empty_with_total(admin_client):
    await _make_album(admin_client, "A", "2026-01-01 00:00:00")
    data = (await admin_client.get("/api/admin/albums", params={"page": 5})).json()
    assert data["items"] == []
    assert data["total"] == 1


async def test_list_albums_paged_counts_still_aggregated(admin_client):
    album_id = await _make_album(admin_client, "Counted", "2026-01-01 00:00:00")
    await admin_client.post(f"/api/admin/albums/{album_id}/photos", json={"photo_paths": ["x.jpg", "y.jpg"]})
    await _make_album(admin_client, "Newer", "2026-02-01 00:00:00")
    items = (await admin_client.get("/api/admin/albums", params={"size": 1, "page": 2})).json()["items"]
    assert items[0]["name"] == "Counted"
    assert items[0]["photo_count"] == 2


async def test_list_albums_extreme_dates_do_not_500(admin_client):
    await _set_tz(admin_client, 540)
    await _make_album(admin_client, "A", "2026-01-01 00:00:00")
    r = await admin_client.get("/api/admin/albums", params={"date_from": "0001-01-01", "date_to": "9999-12-31"})
    assert r.status_code == 200
    assert _names(r) == ["A"]


async def _set_views(album_id, views):
    import aiosqlite
    from backend.models.database import _db_path

    async with aiosqlite.connect(_db_path()) as db:
        await db.execute("UPDATE albums SET view_count = ? WHERE id = ?", (views, album_id))
        await db.commit()


async def _make_viewed_albums(admin_client):
    for name, created, views in [
        ("low", "2026-01-01 00:00:00", 1),
        ("high", "2026-01-02 00:00:00", 50),
        ("mid", "2026-01-03 00:00:00", 10),
    ]:
        await _set_views(await _make_album(admin_client, name, created), views)


async def test_list_albums_sort_by_views_desc(admin_client):
    await _make_viewed_albums(admin_client)
    r = await admin_client.get("/api/admin/albums", params={"sort_by": "view_count", "sort_dir": "desc"})
    assert _names(r) == ["high", "mid", "low"]


async def test_list_albums_sort_by_views_asc(admin_client):
    await _make_viewed_albums(admin_client)
    r = await admin_client.get("/api/admin/albums", params={"sort_by": "view_count", "sort_dir": "asc"})
    assert _names(r) == ["low", "mid", "high"]


async def test_list_albums_sort_by_views_defaults_desc(admin_client):
    await _make_viewed_albums(admin_client)
    r = await admin_client.get("/api/admin/albums", params={"sort_by": "view_count"})
    assert _names(r) == ["high", "mid", "low"]


async def test_list_albums_sort_by_views_ties_newest_first(admin_client):
    await _make_album(admin_client, "old", "2026-01-01 00:00:00")
    await _make_album(admin_client, "new", "2026-01-02 00:00:00")
    for d in ("desc", "asc"):
        r = await admin_client.get("/api/admin/albums", params={"sort_by": "view_count", "sort_dir": d})
        assert _names(r) == ["new", "old"]


async def test_list_albums_sort_by_views_paginates_in_order(admin_client):
    await _make_viewed_albums(admin_client)
    p1 = await admin_client.get("/api/admin/albums", params={"sort_by": "view_count", "page": 1, "size": 2})
    p2 = await admin_client.get("/api/admin/albums", params={"sort_by": "view_count", "page": 2, "size": 2})
    assert _names(p1) == ["high", "mid"]
    assert _names(p2) == ["low"]


async def test_list_albums_sort_by_views_with_search(admin_client):
    await _set_views(await _make_album(admin_client, "trip A", "2026-01-01 00:00:00"), 5)
    await _set_views(await _make_album(admin_client, "trip B", "2026-01-02 00:00:00"), 9)
    await _set_views(await _make_album(admin_client, "other", "2026-01-03 00:00:00"), 99)
    r = await admin_client.get("/api/admin/albums", params={"q": "trip", "sort_by": "view_count"})
    assert _names(r) == ["trip B", "trip A"]


async def test_list_albums_sort_created_at_asc(admin_client):
    await _make_album(admin_client, "old", "2026-01-01 00:00:00")
    await _make_album(admin_client, "new", "2026-01-02 00:00:00")
    r = await admin_client.get("/api/admin/albums", params={"sort_dir": "asc"})
    assert _names(r) == ["old", "new"]


@pytest.mark.parametrize("params", [
    {"page": 0},
    {"page": 10**18},
    {"size": 0},
    {"size": 101},
    {"date_from": "2026-13-01"},
    {"date_to": "not-a-date"},
    {"date_from": "2026-10-02", "date_to": "2026-10-01"},
    {"sort_by": "name"},
    {"sort_by": "view_count; DROP TABLE albums"},
    {"sort_dir": "up"},
])
async def test_list_albums_invalid_params_422(admin_client, params):
    r = await admin_client.get("/api/admin/albums", params=params)
    assert r.status_code == 422


async def test_date_facets_groups_by_server_timezone(admin_client):
    await _set_tz(admin_client, 540)
    await _make_album(admin_client, "a", "2026-09-30 15:00:00")  # KST 2026-10
    await _make_album(admin_client, "b", "2026-10-10 00:00:00")  # KST 2026-10
    await _make_album(admin_client, "c", "2026-09-01 00:00:00")  # KST 2026-09
    await _make_album(admin_client, "d", "2025-12-31 15:00:00")  # KST 2026-01
    await _make_album(admin_client, "e", "2025-12-31 14:00:00")  # KST 2025-12
    r = await admin_client.get("/api/admin/albums/date-facets")
    assert r.status_code == 200
    assert r.json() == {"years": [
        {"year": 2026, "count": 4, "months": [
            {"month": 10, "count": 2}, {"month": 9, "count": 1}, {"month": 1, "count": 1},
        ]},
        {"year": 2025, "count": 1, "months": [{"month": 12, "count": 1}]},
    ]}


async def test_date_facets_respects_query(admin_client):
    await _make_album(admin_client, "trip", "2026-05-01 00:00:00")
    await _make_album(admin_client, "party", "2025-05-01 00:00:00")
    r = await admin_client.get("/api/admin/albums/date-facets", params={"q": "trip"})
    assert [y["year"] for y in r.json()["years"]] == [2026]


async def test_date_facets_empty(admin_client):
    r = await admin_client.get("/api/admin/albums/date-facets")
    assert r.json() == {"years": []}


async def test_date_facets_requires_auth(client):
    r = await client.get("/api/admin/albums/date-facets")
    assert r.status_code == 401
