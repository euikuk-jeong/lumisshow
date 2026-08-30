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


async def test_album_next_expires_at(admin_client):
    album_id = (await admin_client.post("/api/admin/albums", json={"name": "Expiry"})).json()["id"]
    r = await admin_client.get("/api/admin/albums")
    assert r.json()[0]["next_expires_at"] is None

    # 만료일 없는 링크만 있으면 여전히 None
    await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    r = await admin_client.get(f"/api/admin/albums/{album_id}")
    assert r.json()["next_expires_at"] is None

    # 만료일 있는 링크가 생기면 그 값을 반환
    await admin_client.post(
        f"/api/admin/albums/{album_id}/links", json={"expires_at": "2099-12-31T00:00:00"},
    )
    r = await admin_client.get("/api/admin/albums")
    assert r.json()[0]["next_expires_at"] is not None

    # 이미 지난 만료일은 후보에서 제외 (활성 링크 취급 안 함)
    await admin_client.post(
        f"/api/admin/albums/{album_id}/links", json={"expires_at": "2000-01-01T00:00:00"},
    )
    r = await admin_client.get(f"/api/admin/albums/{album_id}")
    assert r.json()["next_expires_at"].startswith("2099")


async def test_album_active_link_count(admin_client):
    album_id = (await admin_client.post("/api/admin/albums", json={"name": "Links"})).json()["id"]
    r = await admin_client.get("/api/admin/albums")
    assert r.json()[0]["active_link_count"] == 0

    await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    link2 = (
        await admin_client.post(f"/api/admin/albums/{album_id}/links", json={})
    ).json()
    r = await admin_client.get("/api/admin/albums")
    assert r.json()[0]["active_link_count"] == 2

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

