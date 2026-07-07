"""admin_people 라우터 테스트 — ai.db 인물/얼굴/잡 API."""

import os

import aiosqlite
import pytest_asyncio


async def _seed_faces(count: int = 3) -> list[int]:
    """ai.db에 테스트 얼굴 행 삽입 (워커 역할 대행). face_id 목록 반환."""
    from backend.models.ai_database import _ai_db_path

    ids = []
    async with aiosqlite.connect(_ai_db_path()) as db:
        for i in range(count):
            cur = await db.execute(
                "INSERT INTO faces (photo_path, bbox, det_score, embedding) VALUES (?, ?, ?, ?)",
                (f"2024/photo_{i}.jpg", "[0,0,10,10]", 0.9, b"\x00" * 8),
            )
            ids.append(cur.lastrowid)
        await db.commit()
    return ids


async def _seed_match(face_id: int, person_id: int, score: float = 0.8) -> None:
    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        await db.execute(
            "INSERT INTO face_matches (face_id, person_id, score) VALUES (?, ?, ?)",
            (face_id, person_id, score),
        )
        await db.commit()


# ── 인물 CRUD ─────────────────────────────────────────────────────────


async def test_people_empty_and_auth_required(admin_client, client):
    r = await admin_client.get("/api/admin/people")
    assert r.status_code == 200 and r.json() == []

    del client.headers["Authorization"]
    r = await client.get("/api/admin/people")
    assert r.status_code in (401, 403)


async def test_create_rename_delete_person(admin_client):
    r = await admin_client.post("/api/admin/people", json={"name": "지우"})
    assert r.status_code == 201
    pid = r.json()["id"]

    # 중복 이름 400
    r = await admin_client.post("/api/admin/people", json={"name": "지우"})
    assert r.status_code == 400
    # 공백 이름 400
    r = await admin_client.post("/api/admin/people", json={"name": "  "})
    assert r.status_code == 400

    r = await admin_client.put(f"/api/admin/people/{pid}", json={"name": "정지우"})
    assert r.status_code == 200 and r.json()["name"] == "정지우"

    r = await admin_client.delete(f"/api/admin/people/{pid}")
    assert r.status_code == 204
    r = await admin_client.delete(f"/api/admin/people/{pid}")
    assert r.status_code == 404


# ── 얼굴 라벨/조회 ────────────────────────────────────────────────────


async def test_label_and_person_faces(admin_client):
    face_ids = await _seed_faces(3)
    pid = (await admin_client.post("/api/admin/people", json={"name": "지우"})).json()["id"]
    await _seed_match(face_ids[1], pid, 0.7)   # 자동 매칭 얼굴
    await _seed_match(face_ids[2], pid, 0.6)   # 매칭됐지만 아래에서 '아님' 교정

    # 라벨 확정 + 무시 교정
    r = await admin_client.post(
        f"/api/admin/faces/{face_ids[0]}/label", json={"person_id": pid}
    )
    assert r.status_code == 200
    r = await admin_client.post(
        f"/api/admin/faces/{face_ids[2]}/label", json={"person_id": None}
    )
    assert r.status_code == 200

    r = await admin_client.get(f"/api/admin/people/{pid}/faces")
    faces = r.json()["faces"]
    # 라벨 1 + 매칭 1 (무시 교정된 face2는 제외)
    assert [(f["face_id"], f["source"]) for f in faces] == [
        (face_ids[0], "labeled"), (face_ids[1], "matched"),
    ]

    r = await admin_client.get(f"/api/admin/people/{pid}/faces?source=labeled")
    assert len(r.json()["faces"]) == 1

    # 인물 목록 카운트 반영
    people = (await admin_client.get("/api/admin/people")).json()
    assert people[0]["labeled_count"] == 1 and people[0]["matched_count"] == 1

    # 사진 목록 (라벨+매칭 사진, 중복 제거)
    photos = (await admin_client.get(f"/api/admin/people/{pid}/photos")).json()["photos"]
    assert photos == ["2024/photo_0.jpg", "2024/photo_1.jpg"]


async def test_person_photos_detail(admin_client):
    """슬라이드쇼용 상세 사진 목록 — URL 구성, 무시 교정 제외, 페이지네이션."""
    face_ids = await _seed_faces(3)
    pid = (await admin_client.post("/api/admin/people", json={"name": "지우"})).json()["id"]
    await admin_client.post(f"/api/admin/faces/{face_ids[0]}/label", json={"person_id": pid})
    await _seed_match(face_ids[1], pid, 0.7)
    await _seed_match(face_ids[2], pid, 0.6)
    await admin_client.post(f"/api/admin/faces/{face_ids[2]}/label", json={"person_id": None})

    r = await admin_client.get(f"/api/admin/people/{pid}/photos-detail")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2 and len(body["photos"]) == 2
    p0 = body["photos"][0]
    assert p0["url"] == "/api/admin/photo?path=2024/photo_0.jpg"
    assert p0["thumb_small_url"] == "/api/admin/thumb?path=2024/photo_0.jpg&size=small"
    assert p0["thumb_medium_url"] == "/api/admin/thumb?path=2024/photo_0.jpg&size=medium"
    assert p0["filename"] == "photo_0.jpg"

    # 페이지네이션: page=2&size=1 → 두 번째 사진만
    r = await admin_client.get(f"/api/admin/people/{pid}/photos-detail?page=2&size=1")
    body = r.json()
    assert body["total"] == 2 and body["page"] == 2
    assert [p["filename"] for p in body["photos"]] == ["photo_1.jpg"]

    # 없는 인물 404
    r = await admin_client.get("/api/admin/people/999/photos-detail")
    assert r.status_code == 404


async def test_person_photos_detail_auth_required(client):
    r = await client.get("/api/admin/people/1/photos-detail")
    assert r.status_code in (401, 403)


async def test_label_validation(admin_client):
    r = await admin_client.post("/api/admin/faces/999/label", json={"person_id": None})
    assert r.status_code == 404  # 없는 얼굴

    face_ids = await _seed_faces(1)
    r = await admin_client.post(
        f"/api/admin/faces/{face_ids[0]}/label", json={"person_id": 999}
    )
    assert r.status_code == 404  # 없는 인물


async def test_unassigned_faces(admin_client):
    face_ids = await _seed_faces(2)
    pid = (await admin_client.post("/api/admin/people", json={"name": "지우"})).json()["id"]
    await _seed_match(face_ids[0], pid)

    r = await admin_client.get("/api/admin/faces/unassigned")
    faces = r.json()["faces"]
    assert [f["face_id"] for f in faces] == [face_ids[1]]


async def test_delete_label_undo(admin_client):
    face_ids = await _seed_faces(1)
    pid = (await admin_client.post("/api/admin/people", json={"name": "지우"})).json()["id"]
    await admin_client.post(f"/api/admin/faces/{face_ids[0]}/label", json={"person_id": pid})

    r = await admin_client.delete(f"/api/admin/faces/{face_ids[0]}/label")
    assert r.status_code == 204
    faces = (await admin_client.get(f"/api/admin/people/{pid}/faces")).json()["faces"]
    assert faces == []


# ── 크롭 서빙 ─────────────────────────────────────────────────────────


async def test_face_crop_serving(admin_client, tmp_path):
    from backend.models.ai_database import faces_dir

    r = await admin_client.get("/api/admin/faces/1/crop")
    assert r.status_code == 404  # 크롭 파일 없음

    os.makedirs(faces_dir(), exist_ok=True)
    with open(os.path.join(faces_dir(), "1.jpg"), "wb") as fp:
        fp.write(b"\xff\xd8\xff\xd9")
    r = await admin_client.get("/api/admin/faces/1/crop")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"


# ── AI 상태/잡 ────────────────────────────────────────────────────────


async def test_ai_status_and_jobs(admin_client):
    r = await admin_client.get("/api/admin/ai/status")
    stats = r.json()
    assert stats["photos"] == 0 and stats["faces"] == 0 and stats["recent_jobs"] == []

    r = await admin_client.post("/api/admin/ai/jobs", json={"type": "scan"})
    assert r.status_code == 201 and r.json()["duplicated"] is False
    job_id = r.json()["id"]

    # 같은 타입 pending 중복 방지
    r = await admin_client.post("/api/admin/ai/jobs", json={"type": "scan"})
    assert r.json() == {"id": job_id, "type": "scan", "duplicated": True}

    r = await admin_client.post("/api/admin/ai/jobs", json={"type": "invalid"})
    assert r.status_code == 400

    stats = (await admin_client.get("/api/admin/ai/status")).json()
    assert stats["recent_jobs"][0]["type"] == "scan"
    assert stats["recent_jobs"][0]["status"] == "pending"
