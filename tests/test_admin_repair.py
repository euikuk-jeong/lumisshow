import os
from pathlib import Path

import aiosqlite


async def _make_album(client, name="A"):
    r = await client.post("/api/admin/albums", json={"name": name})
    assert r.status_code == 201
    return r.json()["id"]


async def _seed_analyzed(path: str, mtime: float = 0.0) -> None:
    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        await db.execute(
            "INSERT INTO photos_analyzed (path, mtime) VALUES (?, ?)", (path, mtime)
        )
        await db.commit()


async def _seed_face_row(photo_path: str) -> int:
    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        cur = await db.execute(
            "INSERT INTO faces (photo_path, bbox, det_score, embedding) VALUES (?, ?, ?, ?)",
            (photo_path, "[0,0,10,10]", 0.9, b"\x00" * 8),
        )
        await db.commit()
        return cur.lastrowid


async def test_repair_no_broken_paths(admin_client):
    photo_root = Path(os.getenv("PHOTO_ROOT"))
    (photo_root / "real.jpg").write_bytes(b"fake")

    album_id = await _make_album(admin_client)
    await admin_client.post(f"/api/admin/albums/{album_id}/photos", json={"photo_paths": ["real.jpg"]})

    r = await admin_client.post(f"/api/admin/albums/{album_id}/repair-paths")
    assert r.status_code == 200
    data = r.json()
    assert data["total_checked"] == 1
    assert data["fixed"] == []
    assert data["ambiguous"] == []
    assert data["not_found"] == []


async def test_repair_fixed(admin_client):
    photo_root = Path(os.getenv("PHOTO_ROOT"))
    (photo_root / "old_dir").mkdir()
    (photo_root / "old_dir" / "photo.jpg").write_bytes(b"fake")

    album_id = await _make_album(admin_client)
    await admin_client.post(f"/api/admin/albums/{album_id}/photos", json={"photo_paths": ["old_dir/photo.jpg"]})

    # 폴더명 변경 시뮬레이션
    (photo_root / "new_dir").mkdir()
    (photo_root / "old_dir" / "photo.jpg").rename(photo_root / "new_dir" / "photo.jpg")
    (photo_root / "old_dir").rmdir()

    r = await admin_client.post(f"/api/admin/albums/{album_id}/repair-paths")
    assert r.status_code == 200
    data = r.json()
    assert len(data["fixed"]) == 1
    assert data["fixed"][0]["old_path"] == "old_dir/photo.jpg"
    assert data["fixed"][0]["new_path"] == "new_dir/photo.jpg"

    r = await admin_client.get(f"/api/admin/albums/{album_id}")
    photo_paths = [p["file_path"] for p in r.json()["photos"]]
    assert "new_dir/photo.jpg" in photo_paths
    assert "old_dir/photo.jpg" not in photo_paths


async def test_repair_ambiguous(admin_client):
    photo_root = Path(os.getenv("PHOTO_ROOT"))
    for d in ["dir1", "dir2"]:
        (photo_root / d).mkdir()
        (photo_root / d / "same.jpg").write_bytes(b"fake")

    album_id = await _make_album(admin_client)
    await admin_client.post(f"/api/admin/albums/{album_id}/photos", json={"photo_paths": ["old/same.jpg"]})

    r = await admin_client.post(f"/api/admin/albums/{album_id}/repair-paths")
    assert r.status_code == 200
    data = r.json()
    assert len(data["ambiguous"]) == 1
    assert data["ambiguous"][0]["old_path"] == "old/same.jpg"
    assert len(data["ambiguous"][0]["candidates"]) == 2
    assert data["fixed"] == []


async def test_repair_not_found(admin_client):
    album_id = await _make_album(admin_client)
    await admin_client.post(f"/api/admin/albums/{album_id}/photos", json={"photo_paths": ["ghost/missing.jpg"]})

    r = await admin_client.post(f"/api/admin/albums/{album_id}/repair-paths")
    assert r.status_code == 200
    data = r.json()
    assert "ghost/missing.jpg" in data["not_found"]
    assert data["fixed"] == []


async def test_repair_updates_cover_path(admin_client):
    photo_root = Path(os.getenv("PHOTO_ROOT"))
    (photo_root / "old").mkdir()
    (photo_root / "old" / "cover.jpg").write_bytes(b"fake")

    album_id = await _make_album(admin_client)
    await admin_client.post(f"/api/admin/albums/{album_id}/photos", json={"photo_paths": ["old/cover.jpg"]})
    await admin_client.put(f"/api/admin/albums/{album_id}", json={"cover_path": "old/cover.jpg"})

    (photo_root / "new").mkdir()
    (photo_root / "old" / "cover.jpg").rename(photo_root / "new" / "cover.jpg")
    (photo_root / "old").rmdir()

    r = await admin_client.post(f"/api/admin/albums/{album_id}/repair-paths")
    assert r.status_code == 200
    assert len(r.json()["fixed"]) == 1

    r = await admin_client.get(f"/api/admin/albums/{album_id}")
    assert r.json()["cover_path"] == "new/cover.jpg"


async def test_repair_only_affects_target_album(admin_client):
    """다른 앨범의 경로는 변경하지 않는다."""
    photo_root = Path(os.getenv("PHOTO_ROOT"))
    (photo_root / "before").mkdir()
    (photo_root / "before" / "shared.jpg").write_bytes(b"fake")

    album_a = await _make_album(admin_client, "A")
    album_b = await _make_album(admin_client, "B")
    for aid in (album_a, album_b):
        await admin_client.post(f"/api/admin/albums/{aid}/photos", json={"photo_paths": ["before/shared.jpg"]})

    (photo_root / "after").mkdir()
    (photo_root / "before" / "shared.jpg").rename(photo_root / "after" / "shared.jpg")
    (photo_root / "before").rmdir()

    # album_a만 복구
    r = await admin_client.post(f"/api/admin/albums/{album_a}/repair-paths")
    assert len(r.json()["fixed"]) == 1

    r_a = await admin_client.get(f"/api/admin/albums/{album_a}")
    r_b = await admin_client.get(f"/api/admin/albums/{album_b}")
    assert r_a.json()["photos"][0]["file_path"] == "after/shared.jpg"
    assert r_b.json()["photos"][0]["file_path"] == "before/shared.jpg"  # 변경 없음


async def test_repair_404_unknown_album(admin_client):
    r = await admin_client.post("/api/admin/albums/9999/repair-paths")
    assert r.status_code == 404


# ── people (photos_analyzed/faces) 경로 복구 ────────────────────────────


async def test_people_repair_no_broken_paths(admin_client):
    photo_root = Path(os.getenv("PHOTO_ROOT"))
    (photo_root / "real.jpg").write_bytes(b"fake")
    await _seed_analyzed("real.jpg")

    r = await admin_client.post("/api/admin/people/repair-paths")
    assert r.status_code == 200
    assert r.json() == {"total_checked": 1, "fixed": [], "ambiguous": [], "not_found": []}


async def test_people_repair_fixed_preserves_face_label(admin_client):
    """rename 복구 후에도 face_id가 유지되어 기존 확정 라벨이 살아있어야 한다."""
    photo_root = Path(os.getenv("PHOTO_ROOT"))
    (photo_root / "old_dir").mkdir()
    (photo_root / "old_dir" / "photo.jpg").write_bytes(b"fake")
    await _seed_analyzed("old_dir/photo.jpg")
    face_id = await _seed_face_row("old_dir/photo.jpg")

    r = await admin_client.post("/api/admin/people", json={"name": "지우"})
    person_id = r.json()["id"]
    r = await admin_client.post(
        f"/api/admin/faces/{face_id}/label", json={"person_id": person_id}
    )
    assert r.status_code == 200

    (photo_root / "new_dir").mkdir()
    (photo_root / "old_dir" / "photo.jpg").rename(photo_root / "new_dir" / "photo.jpg")
    (photo_root / "old_dir").rmdir()

    r = await admin_client.post("/api/admin/people/repair-paths")
    assert r.status_code == 200
    data = r.json()
    assert data["fixed"] == [{"old_path": "old_dir/photo.jpg", "new_path": "new_dir/photo.jpg"}]

    r = await admin_client.get(f"/api/admin/people/{person_id}/faces?source=labeled")
    faces = r.json()["faces"]
    assert len(faces) == 1
    assert faces[0]["face_id"] == face_id
    assert faces[0]["photo_path"] == "new_dir/photo.jpg"


async def test_people_repair_ambiguous(admin_client):
    photo_root = Path(os.getenv("PHOTO_ROOT"))
    for d in ["dir1", "dir2"]:
        (photo_root / d).mkdir()
        (photo_root / d / "same.jpg").write_bytes(b"fake")
    await _seed_analyzed("old/same.jpg")

    r = await admin_client.post("/api/admin/people/repair-paths")
    assert r.status_code == 200
    data = r.json()
    assert len(data["ambiguous"]) == 1
    assert data["ambiguous"][0]["old_path"] == "old/same.jpg"
    assert sorted(data["ambiguous"][0]["candidates"]) == ["dir1/same.jpg", "dir2/same.jpg"]
    assert data["fixed"] == []


async def test_people_repair_not_found_leaves_row_intact(admin_client):
    await _seed_analyzed("ghost/missing.jpg")

    r = await admin_client.post("/api/admin/people/repair-paths")
    assert r.status_code == 200
    data = r.json()
    assert data["not_found"] == ["ghost/missing.jpg"]
    assert data["fixed"] == []

    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        async with db.execute("SELECT path FROM photos_analyzed") as cur:
            rows = await cur.fetchall()
    assert [r[0] for r in rows] == ["ghost/missing.jpg"]  # 변경 없음


async def test_people_repair_requires_auth(client):
    r = await client.post("/api/admin/people/repair-paths")
    assert r.status_code in (401, 403)
