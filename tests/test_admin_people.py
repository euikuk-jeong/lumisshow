"""admin_people 라우터 테스트 — ai.db 인물/얼굴/잡 API."""

import os

import aiosqlite
import numpy as np
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


async def _seed_faces_with_embeddings(vectors: list[list[float]]) -> list[int]:
    """임베딩 값을 직접 지정해 ai.db에 얼굴 삽입 (유사도 검색 테스트용)."""
    from backend.models.ai_database import _ai_db_path

    ids = []
    async with aiosqlite.connect(_ai_db_path()) as db:
        for i, vec in enumerate(vectors):
            cur = await db.execute(
                "INSERT INTO faces (photo_path, bbox, det_score, embedding) VALUES (?, ?, ?, ?)",
                (f"2024/photo_{i}.jpg", "[0,0,10,10]", 0.9,
                 np.asarray(vec, dtype=np.float32).tobytes()),
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


async def test_get_person(admin_client, client):
    pid = (await admin_client.post("/api/admin/people", json={"name": "지우"})).json()["id"]

    r = await admin_client.get(f"/api/admin/people/{pid}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == pid and body["name"] == "지우"
    assert body["labeled_count"] == 0 and body["matched_count"] == 0

    r = await admin_client.get("/api/admin/people/999")
    assert r.status_code == 404

    del client.headers["Authorization"]
    r = await client.get(f"/api/admin/people/{pid}")
    assert r.status_code in (401, 403)


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

    # source=labeled — 확정 사진만 (매칭된 photo_1.jpg 제외)
    photos = (await admin_client.get(f"/api/admin/people/{pid}/photos?source=labeled")).json()["photos"]
    assert photos == ["2024/photo_0.jpg"]

    # 잘못된 source 422
    r = await admin_client.get(f"/api/admin/people/{pid}/photos?source=bogus")
    assert r.status_code == 422


async def test_person_faces_max_score_and_offset(admin_client):
    """max_score — 임계값 미리보기용 필터, offset/limit — 더보기 페이지네이션."""
    face_ids = await _seed_faces(3)
    pid = (await admin_client.post("/api/admin/people", json={"name": "지우"})).json()["id"]
    await _seed_match(face_ids[0], pid, 0.9)
    await _seed_match(face_ids[1], pid, 0.7)
    await _seed_match(face_ids[2], pid, 0.5)

    r = await admin_client.get(f"/api/admin/people/{pid}/faces?source=matched&max_score=0.7")
    assert r.status_code == 200
    faces = r.json()["faces"]
    assert [f["face_id"] for f in faces] == [face_ids[1], face_ids[2]]

    # 경계값 포함 여부: max_score와 정확히 같은 점수도 포함(<=)
    r = await admin_client.get(f"/api/admin/people/{pid}/faces?source=matched&max_score=0.9")
    faces = r.json()["faces"]
    assert [f["face_id"] for f in faces] == [face_ids[0], face_ids[1], face_ids[2]]

    r = await admin_client.get(f"/api/admin/people/{pid}/faces?source=matched&limit=1&offset=1")
    faces = r.json()["faces"]
    assert [f["face_id"] for f in faces] == [face_ids[1]]

    r = await admin_client.get(f"/api/admin/people/{pid}/faces?source=matched&max_score=1.5")
    assert r.status_code == 422


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

    # size=0은 비허용 (전체 EXIF 일괄 읽기 방지)
    r = await admin_client.get(f"/api/admin/people/{pid}/photos-detail?size=0")
    assert r.status_code == 422

    # 범위 밖 페이지는 빈 목록 (total은 유지)
    r = await admin_client.get(f"/api/admin/people/{pid}/photos-detail?page=9&size=1")
    body = r.json()
    assert body["total"] == 2 and body["photos"] == []

    # 없는 인물 404
    r = await admin_client.get("/api/admin/people/999/photos-detail")
    assert r.status_code == 404


async def test_person_photos_detail_source_labeled(admin_client):
    """source=labeled — 확정(라벨) 얼굴 사진만, 추정 매칭 제외. file_path 포함."""
    face_ids = await _seed_faces(3)
    pid = (await admin_client.post("/api/admin/people", json={"name": "지우"})).json()["id"]
    await admin_client.post(f"/api/admin/faces/{face_ids[0]}/label", json={"person_id": pid})
    await _seed_match(face_ids[1], pid, 0.7)   # 추정 매칭 — labeled에서 제외
    await _seed_match(face_ids[2], pid, 0.6)
    await admin_client.post(f"/api/admin/faces/{face_ids[2]}/label", json={"person_id": None})

    r = await admin_client.get(f"/api/admin/people/{pid}/photos-detail?source=labeled")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert [p["filename"] for p in body["photos"]] == ["photo_0.jpg"]
    assert body["photos"][0]["file_path"] == "2024/photo_0.jpg"

    # 기본(all)은 확정+추정 모두
    r = await admin_client.get(f"/api/admin/people/{pid}/photos-detail")
    assert r.json()["total"] == 2

    # 잘못된 source 422
    r = await admin_client.get(f"/api/admin/people/{pid}/photos-detail?source=bogus")
    assert r.status_code == 422


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


async def test_similar_faces(admin_client):
    ids = await _seed_faces_with_embeddings([
        [1.0, 0.0, 0.0],   # 기준
        [0.9, 0.1, 0.0],   # 기준과 가까움
        [0.0, 1.0, 0.0],   # 기준과 직교(안 비슷함)
    ])

    r = await admin_client.get(f"/api/admin/faces/{ids[0]}/similar")
    assert r.status_code == 200
    faces = r.json()["faces"]
    # 기준 얼굴 자신(유사도 1.0)이 최상단, 그다음 가까운 순
    assert [f["face_id"] for f in faces] == [ids[0], ids[1], ids[2]]
    assert faces[0]["score"] == 1.0
    assert faces[1]["score"] > faces[2]["score"]

    # 없는 얼굴 404
    r = await admin_client.get("/api/admin/faces/999/similar")
    assert r.status_code == 404

    # 이미 라벨된 얼굴은 결과에서 제외 (기준 얼굴 자신은 라벨 여부와 무관하게 포함)
    pid = (await admin_client.post("/api/admin/people", json={"name": "지우"})).json()["id"]
    await admin_client.post(f"/api/admin/faces/{ids[1]}/label", json={"person_id": pid})
    r = await admin_client.get(f"/api/admin/faces/{ids[0]}/similar")
    assert [f["face_id"] for f in r.json()["faces"]] == [ids[0], ids[2]]


async def test_unassigned_faces(admin_client):
    face_ids = await _seed_faces(2)
    pid = (await admin_client.post("/api/admin/people", json={"name": "지우"})).json()["id"]
    await _seed_match(face_ids[0], pid)

    r = await admin_client.get("/api/admin/faces/unassigned")
    faces = r.json()["faces"]
    assert [f["face_id"] for f in faces] == [face_ids[1]]


async def test_ignored_faces(admin_client, client):
    face_ids = await _seed_faces(3)
    pid = (await admin_client.post("/api/admin/people", json={"name": "지우"})).json()["id"]

    # face0·face1 무시, face2는 인물 라벨
    r = await admin_client.post(
        "/api/admin/faces/batch-label", json={"face_ids": face_ids[:2], "person_id": None}
    )
    assert r.status_code == 200
    await admin_client.post(f"/api/admin/faces/{face_ids[2]}/label", json={"person_id": pid})

    r = await admin_client.get("/api/admin/faces/ignored")
    assert r.status_code == 200
    faces = r.json()["faces"]
    assert {f["face_id"] for f in faces} == {face_ids[0], face_ids[1]}
    assert all(f["labeled_at"] is not None for f in faces)

    # 페이지네이션
    r = await admin_client.get("/api/admin/faces/ignored?limit=1&offset=1")
    assert len(r.json()["faces"]) == 1

    # 무시 해제(라벨 삭제) 후 목록에서 빠짐 + 미분류로 복귀
    r = await admin_client.delete(f"/api/admin/faces/{face_ids[0]}/label")
    assert r.status_code == 204
    faces = (await admin_client.get("/api/admin/faces/ignored")).json()["faces"]
    assert [f["face_id"] for f in faces] == [face_ids[1]]
    unassigned = (await admin_client.get("/api/admin/faces/unassigned")).json()["faces"]
    assert face_ids[0] in {f["face_id"] for f in unassigned}

    # 무시된 얼굴을 인물로 재지정하면 목록에서 빠짐
    r = await admin_client.post(
        "/api/admin/faces/batch-label", json={"face_ids": [face_ids[1]], "person_id": pid}
    )
    assert r.status_code == 200
    assert (await admin_client.get("/api/admin/faces/ignored")).json()["faces"] == []

    # 인증 필요
    del client.headers["Authorization"]
    r = await client.get("/api/admin/faces/ignored")
    assert r.status_code in (401, 403)


async def test_batch_label_faces(admin_client):
    face_ids = await _seed_faces(3)
    pid = (await admin_client.post("/api/admin/people", json={"name": "지우"})).json()["id"]

    r = await admin_client.post(
        "/api/admin/faces/batch-label",
        json={"face_ids": face_ids[:2], "person_id": pid},
    )
    assert r.status_code == 200 and r.json() == {"count": 2}

    faces = (await admin_client.get(f"/api/admin/people/{pid}/faces?source=labeled")).json()["faces"]
    assert {f["face_id"] for f in faces} == {face_ids[0], face_ids[1]}

    # 빈 목록 400
    r = await admin_client.post("/api/admin/faces/batch-label", json={"face_ids": []})
    assert r.status_code == 400

    # 없는 인물 404
    r = await admin_client.post(
        "/api/admin/faces/batch-label", json={"face_ids": [face_ids[2]], "person_id": 999}
    )
    assert r.status_code == 404

    # 없는 얼굴 포함 시 404 (전체 롤백 — 존재하는 얼굴도 라벨 안 됨)
    r = await admin_client.post(
        "/api/admin/faces/batch-label", json={"face_ids": [face_ids[2], 999], "person_id": pid}
    )
    assert r.status_code == 404
    faces = (await admin_client.get(f"/api/admin/people/{pid}/faces?source=labeled")).json()["faces"]
    assert face_ids[2] not in {f["face_id"] for f in faces}


async def test_batch_unlabel_faces(admin_client, client):
    face_ids = await _seed_faces(3)
    pid = (await admin_client.post("/api/admin/people", json={"name": "지우"})).json()["id"]
    await admin_client.post(
        "/api/admin/faces/batch-label", json={"face_ids": face_ids, "person_id": pid}
    )

    # 두 개만 한 번에 라벨 삭제 (httpx delete()는 body 미지원 — request()로 호출)
    r = await admin_client.request(
        "DELETE", "/api/admin/faces/batch-unlabel", json={"face_ids": face_ids[:2]}
    )
    assert r.status_code == 204

    faces = (await admin_client.get(f"/api/admin/people/{pid}/faces?source=labeled")).json()["faces"]
    assert {f["face_id"] for f in faces} == {face_ids[2]}

    # 빈 목록 400
    r = await admin_client.request(
        "DELETE", "/api/admin/faces/batch-unlabel", json={"face_ids": []}
    )
    assert r.status_code == 400

    # 존재하지 않는 face_id가 섞여도 존재하는 것만 조용히 삭제
    r = await admin_client.request(
        "DELETE", "/api/admin/faces/batch-unlabel", json={"face_ids": [face_ids[2], 999]}
    )
    assert r.status_code == 204
    faces = (await admin_client.get(f"/api/admin/people/{pid}/faces?source=labeled")).json()["faces"]
    assert faces == []

    # 인증 필요
    del client.headers["Authorization"]
    r = await client.request(
        "DELETE", "/api/admin/faces/batch-unlabel", json={"face_ids": face_ids[:1]}
    )
    assert r.status_code in (401, 403)


async def test_unlabel_person_photo(admin_client, client):
    """사진 경로 기준 라벨 일괄 해제 — 전체 사진 라이트박스 '확정 해제' 버튼용."""
    face_ids = await _seed_faces(3)  # photo_0/1/2.jpg 각 1개 얼굴
    pid = (await admin_client.post("/api/admin/people", json={"name": "지우"})).json()["id"]
    await admin_client.post(f"/api/admin/faces/{face_ids[0]}/label", json={"person_id": pid})
    await admin_client.post(f"/api/admin/faces/{face_ids[1]}/label", json={"person_id": pid})

    r = await admin_client.delete(
        f"/api/admin/people/{pid}/photo-label", params={"path": "2024/photo_0.jpg"}
    )
    assert r.status_code == 204

    faces = (await admin_client.get(f"/api/admin/people/{pid}/faces?source=labeled")).json()["faces"]
    assert {f["face_id"] for f in faces} == {face_ids[1]}

    # path 쿼리 파라미터 누락 422
    r = await admin_client.delete(f"/api/admin/people/{pid}/photo-label")
    assert r.status_code == 422

    # 해당 사진에 라벨이 없어도(이미 해제됐거나 원래 없음) 조용히 204
    r = await admin_client.delete(
        f"/api/admin/people/{pid}/photo-label", params={"path": "2024/photo_0.jpg"}
    )
    assert r.status_code == 204

    # 없는 인물 404
    r = await admin_client.delete(
        "/api/admin/people/999/photo-label", params={"path": "2024/photo_0.jpg"}
    )
    assert r.status_code == 404

    # 인증 필요
    del client.headers["Authorization"]
    r = await client.delete(
        f"/api/admin/people/{pid}/photo-label", params={"path": "2024/photo_1.jpg"}
    )
    assert r.status_code in (401, 403)


async def test_confirm_matched_by_score(admin_client):
    face_ids = await _seed_faces(3)
    pid = (await admin_client.post("/api/admin/people", json={"name": "지우"})).json()["id"]
    await _seed_match(face_ids[0], pid, 0.8)
    await _seed_match(face_ids[1], pid, 0.6)
    await _seed_match(face_ids[2], pid, 0.5)

    r = await admin_client.post(
        f"/api/admin/people/{pid}/confirm-matched", json={"min_score": 0.7}
    )
    assert r.status_code == 200 and r.json() == {"count": 1}

    faces = (await admin_client.get(f"/api/admin/people/{pid}/faces?source=labeled")).json()["faces"]
    assert [f["face_id"] for f in faces] == [face_ids[0]]

    matched = (await admin_client.get(f"/api/admin/people/{pid}/faces?source=matched")).json()["faces"]
    assert {f["face_id"] for f in matched} == {face_ids[1], face_ids[2]}

    # 이미 확정된 얼굴은 재확정 대상에서 자동 제외 (count 0)
    r = await admin_client.post(
        f"/api/admin/people/{pid}/confirm-matched", json={"min_score": 0.7}
    )
    assert r.json() == {"count": 0}

    # 없는 인물 404
    r = await admin_client.post(
        "/api/admin/people/999/confirm-matched", json={"min_score": 0.5}
    )
    assert r.status_code == 404

    # 범위 밖 min_score 422
    r = await admin_client.post(
        f"/api/admin/people/{pid}/confirm-matched", json={"min_score": 1.5}
    )
    assert r.status_code == 422


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


# ── AI 설정 (야간 스캔 시각) ──────────────────────────────────────────


async def test_ai_settings_get_and_update(admin_client, client):
    # 미설정 시 null
    r = await admin_client.get("/api/admin/ai/settings")
    assert r.status_code == 200 and r.json() == {"scan_hour": None}

    # 설정 저장 → 조회 반영
    r = await admin_client.patch("/api/admin/ai/settings", json={"scan_hour": 4})
    assert r.status_code == 200 and r.json() == {"scan_hour": 4}
    r = await admin_client.get("/api/admin/ai/settings")
    assert r.json() == {"scan_hour": 4}

    # 덮어쓰기
    await admin_client.patch("/api/admin/ai/settings", json={"scan_hour": 23})
    assert (await admin_client.get("/api/admin/ai/settings")).json() == {"scan_hour": 23}

    # 범위 밖 422
    r = await admin_client.patch("/api/admin/ai/settings", json={"scan_hour": 24})
    assert r.status_code == 422
    r = await admin_client.patch("/api/admin/ai/settings", json={"scan_hour": -1})
    assert r.status_code == 422

    # 인증 필요
    del client.headers["Authorization"]
    r = await client.get("/api/admin/ai/settings")
    assert r.status_code in (401, 403)
    r = await client.patch("/api/admin/ai/settings", json={"scan_hour": 3})
    assert r.status_code in (401, 403)
