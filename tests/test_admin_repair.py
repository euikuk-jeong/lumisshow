import os
from pathlib import Path


async def test_repair_no_broken_paths(admin_client):
    photo_root = Path(os.getenv("PHOTO_ROOT"))
    (photo_root / "real.jpg").write_bytes(b"fake")

    await admin_client.post("/api/admin/albums", json={"name": "A", "photo_paths": ["real.jpg"]})

    r = await admin_client.post("/api/admin/repair-paths")
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

    r = await admin_client.post("/api/admin/albums", json={"name": "A", "photo_paths": ["old_dir/photo.jpg"]})
    album_id = r.json()["id"]

    # 폴더명 변경 시뮬레이션
    (photo_root / "new_dir").mkdir()
    (photo_root / "old_dir" / "photo.jpg").rename(photo_root / "new_dir" / "photo.jpg")
    (photo_root / "old_dir").rmdir()

    r = await admin_client.post("/api/admin/repair-paths")
    assert r.status_code == 200
    data = r.json()
    assert len(data["fixed"]) == 1
    assert data["fixed"][0]["old_path"] == "old_dir/photo.jpg"
    assert data["fixed"][0]["new_path"] == "new_dir/photo.jpg"

    # 앨범 경로가 실제로 갱신됐는지 확인
    r = await admin_client.get(f"/api/admin/albums/{album_id}")
    photo_paths = [p["file_path"] for p in r.json()["photos"]]
    assert "new_dir/photo.jpg" in photo_paths
    assert "old_dir/photo.jpg" not in photo_paths


async def test_repair_ambiguous(admin_client):
    photo_root = Path(os.getenv("PHOTO_ROOT"))
    for d in ["dir1", "dir2"]:
        (photo_root / d).mkdir()
        (photo_root / d / "same.jpg").write_bytes(b"fake")

    # 실제로 없는 경로로 앨범 등록
    await admin_client.post("/api/admin/albums", json={"name": "A", "photo_paths": ["old/same.jpg"]})

    r = await admin_client.post("/api/admin/repair-paths")
    assert r.status_code == 200
    data = r.json()
    assert len(data["ambiguous"]) == 1
    assert data["ambiguous"][0]["old_path"] == "old/same.jpg"
    assert len(data["ambiguous"][0]["candidates"]) == 2
    assert data["fixed"] == []


async def test_repair_not_found(admin_client):
    await admin_client.post("/api/admin/albums", json={"name": "A", "photo_paths": ["ghost/missing.jpg"]})

    r = await admin_client.post("/api/admin/repair-paths")
    assert r.status_code == 200
    data = r.json()
    assert "ghost/missing.jpg" in data["not_found"]
    assert data["fixed"] == []


async def test_repair_updates_cover_path(admin_client):
    photo_root = Path(os.getenv("PHOTO_ROOT"))
    (photo_root / "old").mkdir()
    (photo_root / "old" / "cover.jpg").write_bytes(b"fake")

    r = await admin_client.post("/api/admin/albums", json={"name": "A", "photo_paths": ["old/cover.jpg"]})
    album_id = r.json()["id"]
    await admin_client.put(f"/api/admin/albums/{album_id}", json={"cover_path": "old/cover.jpg"})

    # 폴더 이동
    (photo_root / "new").mkdir()
    (photo_root / "old" / "cover.jpg").rename(photo_root / "new" / "cover.jpg")
    (photo_root / "old").rmdir()

    r = await admin_client.post("/api/admin/repair-paths")
    assert r.status_code == 200
    assert len(r.json()["fixed"]) == 1

    r = await admin_client.get(f"/api/admin/albums/{album_id}")
    assert r.json()["cover_path"] == "new/cover.jpg"


async def test_repair_deduplicates_across_albums(admin_client):
    """같은 깨진 경로가 여러 앨범에 있을 때 모두 수정된다."""
    photo_root = Path(os.getenv("PHOTO_ROOT"))
    (photo_root / "before").mkdir()
    (photo_root / "before" / "shared.jpg").write_bytes(b"fake")

    await admin_client.post("/api/admin/albums", json={"name": "A1", "photo_paths": ["before/shared.jpg"]})
    await admin_client.post("/api/admin/albums", json={"name": "A2", "photo_paths": ["before/shared.jpg"]})

    (photo_root / "after").mkdir()
    (photo_root / "before" / "shared.jpg").rename(photo_root / "after" / "shared.jpg")
    (photo_root / "before").rmdir()

    r = await admin_client.post("/api/admin/repair-paths")
    data = r.json()
    # 고유 경로 기준으로 1건만 fix됨
    assert len(data["fixed"]) == 1
    assert data["fixed"][0]["new_path"] == "after/shared.jpg"
