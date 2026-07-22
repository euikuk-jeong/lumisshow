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
    assert r.json() == {"total_checked": 1, "proposed": [], "ambiguous": [], "not_found": []}


async def test_people_repair_proposes_without_applying(admin_client):
    """스캔은 제안만 쌓는다 — approve 전엔 photos_analyzed/faces가 그대로여야 한다."""
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
    assert len(data["proposed"]) == 1
    proposal = data["proposed"][0]
    assert proposal["old_path"] == "old_dir/photo.jpg"
    assert proposal["new_path"] == "new_dir/photo.jpg"
    assert "id" in proposal

    # 승인 전 — 아직 old_path 그대로
    r = await admin_client.get(f"/api/admin/people/{person_id}/faces?source=labeled")
    assert r.json()["faces"][0]["photo_path"] == "old_dir/photo.jpg"


async def test_people_repair_approve_applies_and_preserves_label(admin_client):
    """제안을 승인해야 실제 UPDATE가 일어나고 face_id 유지로 라벨이 보존된다."""
    photo_root = Path(os.getenv("PHOTO_ROOT"))
    (photo_root / "old_dir").mkdir()
    (photo_root / "old_dir" / "photo.jpg").write_bytes(b"fake")
    await _seed_analyzed("old_dir/photo.jpg")
    face_id = await _seed_face_row("old_dir/photo.jpg")

    r = await admin_client.post("/api/admin/people", json={"name": "지우"})
    person_id = r.json()["id"]
    await admin_client.post(f"/api/admin/faces/{face_id}/label", json={"person_id": person_id})

    (photo_root / "new_dir").mkdir()
    (photo_root / "old_dir" / "photo.jpg").rename(photo_root / "new_dir" / "photo.jpg")
    (photo_root / "old_dir").rmdir()

    r = await admin_client.post("/api/admin/people/repair-paths")
    proposal_id = r.json()["proposed"][0]["id"]

    r = await admin_client.post(f"/api/admin/people/path-repairs/{proposal_id}/approve")
    assert r.status_code == 200
    assert r.json() == {"old_path": "old_dir/photo.jpg", "new_path": "new_dir/photo.jpg"}

    r = await admin_client.get(f"/api/admin/people/{person_id}/faces?source=labeled")
    faces = r.json()["faces"]
    assert len(faces) == 1
    assert faces[0]["face_id"] == face_id
    assert faces[0]["photo_path"] == "new_dir/photo.jpg"

    # 승인 후엔 대기열에서 사라져야 한다
    r = await admin_client.get("/api/admin/people/path-repairs")
    assert r.json()["repairs"] == []


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
    assert data["proposed"] == []


async def test_people_repair_not_found_leaves_row_intact(admin_client):
    await _seed_analyzed("ghost/missing.jpg")

    r = await admin_client.post("/api/admin/people/repair-paths")
    assert r.status_code == 200
    data = r.json()
    assert data["not_found"] == ["ghost/missing.jpg"]
    assert data["proposed"] == []

    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        async with db.execute("SELECT path FROM photos_analyzed") as cur:
            rows = await cur.fetchall()
    assert [r[0] for r in rows] == ["ghost/missing.jpg"]  # 변경 없음


async def test_people_repair_duplicate_orphan_basenames_no_pk_collision(admin_client):
    """orphan 쪽에 동명 basename이 2개면(카메라 IMG_0001.jpg류) 후보가 1개뿐이라도
    자동 매칭하지 않고 ambiguous 처리해야 한다 — 순차 승인 시 두 번째 old_path가
    이미 선점된 path로 UPDATE를 시도해 PRIMARY KEY 충돌(500)이 나는 걸 막기 위함."""
    photo_root = Path(os.getenv("PHOTO_ROOT"))
    (photo_root / "archive").mkdir()
    (photo_root / "archive" / "IMG_0001.jpg").write_bytes(b"fake")
    await _seed_analyzed("2023/IMG_0001.jpg")
    await _seed_analyzed("backup/IMG_0001.jpg")

    r = await admin_client.post("/api/admin/people/repair-paths")
    assert r.status_code == 200
    data = r.json()
    assert data["proposed"] == []
    assert {a["old_path"] for a in data["ambiguous"]} == {
        "2023/IMG_0001.jpg", "backup/IMG_0001.jpg",
    }
    assert all(a["candidates"] == ["archive/IMG_0001.jpg"] for a in data["ambiguous"])

    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        async with db.execute("SELECT path FROM photos_analyzed ORDER BY path") as cur:
            rows = await cur.fetchall()
    assert [r[0] for r in rows] == ["2023/IMG_0001.jpg", "backup/IMG_0001.jpg"]  # 변경 없음


async def test_people_repair_requires_auth(client):
    r = await client.post("/api/admin/people/repair-paths")
    assert r.status_code in (401, 403)
    r = await client.get("/api/admin/people/path-repairs")
    assert r.status_code in (401, 403)
    r = await client.post("/api/admin/people/path-repairs/1/approve")
    assert r.status_code in (401, 403)
    r = await client.post("/api/admin/people/path-repairs/1/reject")
    assert r.status_code in (401, 403)
    r = await client.post("/api/admin/people/path-repairs/approve-all")
    assert r.status_code in (401, 403)


# ── path-repairs 승인 대기열 ────────────────────────────────────────────


async def _propose_rename(admin_client, old_dir: str, new_dir: str, filename: str = "photo.jpg") -> int:
    photo_root = Path(os.getenv("PHOTO_ROOT"))
    (photo_root / old_dir).mkdir(parents=True, exist_ok=True)
    (photo_root / old_dir / filename).write_bytes(b"fake")
    await _seed_analyzed(f"{old_dir}/{filename}")

    (photo_root / new_dir).mkdir(parents=True, exist_ok=True)
    (photo_root / old_dir / filename).rename(photo_root / new_dir / filename)
    (photo_root / old_dir).rmdir()

    r = await admin_client.post("/api/admin/people/repair-paths")
    return r.json()["proposed"][0]["id"]


async def test_path_repairs_list_and_reject(admin_client):
    repair_id = await _propose_rename(admin_client, "old", "new")

    r = await admin_client.get("/api/admin/people/path-repairs")
    assert r.status_code == 200
    repairs = r.json()["repairs"]
    assert len(repairs) == 1
    assert repairs[0]["id"] == repair_id
    assert repairs[0]["source"] == "manual"

    r = await admin_client.post(f"/api/admin/people/path-repairs/{repair_id}/reject")
    assert r.status_code == 200
    assert r.json() == {"id": repair_id, "status": "rejected"}

    r = await admin_client.get("/api/admin/people/path-repairs")
    assert r.json()["repairs"] == []  # 거부된 건 목록에 안 보임


async def test_path_repairs_approve_all(admin_client):
    id1 = await _propose_rename(admin_client, "old1", "new1", "a.jpg")
    id2 = await _propose_rename(admin_client, "old2", "new2", "b.jpg")

    r = await admin_client.post("/api/admin/people/path-repairs/approve-all")
    assert r.status_code == 200
    data = r.json()
    assert {a["old_path"] for a in data["applied"]} == {"old1/a.jpg", "old2/b.jpg"}
    assert data["failed"] == []

    r = await admin_client.get("/api/admin/people/path-repairs")
    assert r.json()["repairs"] == []


async def test_path_repairs_approve_all_mixed_batch(admin_client):
    """한쪽이 충돌해도 나머지는 정상 적용되고, 실패분은 제안이 그대로 남아야 한다
    (같은 커넥션에서 IntegrityError 이후에도 이어지는 UPDATE/commit이 유효한지 검증)."""
    clean_id = await _propose_rename(admin_client, "old1", "new1", "a.jpg")
    conflict_id = await _propose_rename(admin_client, "old2", "new2", "b.jpg")
    # conflict_id의 new_path가 이미 분석된 상태를 레이스처럼 재현 → approve 시 충돌
    await _seed_analyzed("new2/b.jpg")

    r = await admin_client.post("/api/admin/people/path-repairs/approve-all")
    assert r.status_code == 200
    data = r.json()
    assert data["applied"] == [{"old_path": "old1/a.jpg", "new_path": "new1/a.jpg"}]
    assert data["failed"] == [{"old_path": "old2/b.jpg", "new_path": "new2/b.jpg"}]

    # 성공분은 실제로 반영됐어야 한다
    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        async with db.execute("SELECT path FROM photos_analyzed ORDER BY path") as cur:
            rows = [r[0] for r in await cur.fetchall()]
    assert "new1/a.jpg" in rows
    assert "old1/a.jpg" not in rows
    assert "old2/b.jpg" in rows  # 실패분은 그대로 orphan 유지

    # 실패분 제안은 삭제되지 않고 남아 admin이 다시 판단할 수 있어야 한다
    r = await admin_client.get("/api/admin/people/path-repairs")
    repairs = r.json()["repairs"]
    assert len(repairs) == 1
    assert repairs[0]["id"] == conflict_id
    assert clean_id != conflict_id


async def test_path_repairs_approve_conflict_returns_409(admin_client):
    repair_id = await _propose_rename(admin_client, "old", "new")
    # new_path가 이미 별도로 분석된 상태를 레이스처럼 재현
    await _seed_analyzed("new/photo.jpg")

    r = await admin_client.post(f"/api/admin/people/path-repairs/{repair_id}/approve")
    assert r.status_code == 409

    # 실패 시 제안은 그대로 남아 있어야 admin이 다시 판단할 수 있다
    r = await admin_client.get("/api/admin/people/path-repairs")
    assert len(r.json()["repairs"]) == 1


async def test_path_repairs_approve_404_unknown_id(admin_client):
    r = await admin_client.post("/api/admin/people/path-repairs/9999/approve")
    assert r.status_code == 404


async def test_path_repairs_reject_404_unknown_id(admin_client):
    r = await admin_client.post("/api/admin/people/path-repairs/9999/reject")
    assert r.status_code == 404
