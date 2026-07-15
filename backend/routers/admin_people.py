"""Phase 2 인물(People) 관리 API — ai.db 기반.

쓰기 대상: persons, face_labels, jobs, ai_settings (그 외 테이블은 AI 워커가 씀).
유효 인물 판정: face_labels가 있으면 그 값이 우선, 없으면 face_matches.
"""

import os
from typing import Optional
from urllib.parse import quote

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from backend.models.ai_database import faces_dir, get_ai_db
from backend.models.database import get_db
from backend.models.schemas import (
    AiSettingsUpdate,
    BatchFaceLabel,
    BatchFaceUnlabel,
    ConfirmByScore,
    FaceLabelSet,
    JobCreate,
    PersonCreate,
    SharePhotosResponse,
    build_share_photo_item,
)
from backend.routers.admin_browse import _admin_image_auth, load_photo_meta
from backend.services.auth import get_current_admin

router = APIRouter(prefix="/api/admin", tags=["admin-people"])

_JOB_TYPES = {"scan", "rematch"}


async def _person_or_404(person_id: int, db) -> None:
    async with db.execute("SELECT id FROM persons WHERE id = ?", (person_id,)) as cur:
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Person not found")


# 인물이 등장하는 사진 판정: 라벨이 있으면 라벨 우선, 없으면 자동 매칭
_PERSON_PHOTOS_FROM = """
    FROM faces f
    LEFT JOIN face_labels fl ON fl.face_id = f.id
    LEFT JOIN face_matches fm ON fm.face_id = f.id
    WHERE (fl.person_id = ?)
       OR (fl.face_id IS NULL AND fm.person_id = ?)
"""

# 확정(라벨)된 얼굴만 — 추정 매칭 제외
_PERSON_PHOTOS_LABELED_FROM = """
    FROM faces f
    JOIN face_labels fl ON fl.face_id = f.id
    WHERE fl.person_id = ?
"""


async def _person_photo_paths(
    person_id: int, db, limit: Optional[int] = None, offset: int = 0,
    labeled_only: bool = False,
) -> list[str]:
    frm = _PERSON_PHOTOS_LABELED_FROM if labeled_only else _PERSON_PHOTOS_FROM
    sql = f"SELECT DISTINCT f.photo_path {frm} ORDER BY f.photo_path"
    params: list = [person_id] if labeled_only else [person_id, person_id]
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params += [limit, offset]
    async with db.execute(sql, params) as cur:
        return [r["photo_path"] for r in await cur.fetchall()]


# ── 인물 CRUD ─────────────────────────────────────────────────────────


@router.get("/people")
async def list_people(_: str = Depends(get_current_admin), db=Depends(get_ai_db)):
    async with db.execute(
        """
        SELECT p.id, p.name, p.created_at,
               (SELECT COUNT(*) FROM face_labels fl
                 WHERE fl.person_id = p.id) AS labeled_count,
               (SELECT COUNT(*) FROM face_matches fm
                 WHERE fm.person_id = p.id
                   AND fm.face_id NOT IN (SELECT face_id FROM face_labels)) AS matched_count,
               (SELECT fl.face_id FROM face_labels fl
                 WHERE fl.person_id = p.id ORDER BY fl.labeled_at LIMIT 1) AS cover_face_id
        FROM persons p ORDER BY labeled_count + matched_count DESC, p.name
        """
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.post("/people", status_code=201)
async def create_person(
    body: PersonCreate, _: str = Depends(get_current_admin), db=Depends(get_ai_db)
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="이름을 입력하세요")
    async with db.execute("SELECT id FROM persons WHERE name = ?", (name,)) as cur:
        if await cur.fetchone() is not None:
            raise HTTPException(status_code=400, detail="이미 존재하는 인물입니다")
    cur = await db.execute("INSERT INTO persons (name) VALUES (?)", (name,))
    await db.commit()
    return {"id": cur.lastrowid, "name": name}


@router.put("/people/{person_id}")
async def rename_person(
    person_id: int, body: PersonCreate,
    _: str = Depends(get_current_admin), db=Depends(get_ai_db),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="이름을 입력하세요")
    await _person_or_404(person_id, db)
    await db.execute("UPDATE persons SET name = ? WHERE id = ?", (name, person_id))
    await db.commit()
    return {"id": person_id, "name": name}


@router.delete("/people/{person_id}", status_code=204)
async def delete_person(
    person_id: int, _: str = Depends(get_current_admin), db=Depends(get_ai_db)
):
    await _person_or_404(person_id, db)
    # face_matches의 잔여 행은 워커 소유 테이블이라 건드리지 않는다.
    # 조회는 항상 persons JOIN이므로 보이지 않으며, 다음 rematch 때 정리된다.
    await db.execute("DELETE FROM face_labels WHERE person_id = ?", (person_id,))
    await db.execute("DELETE FROM persons WHERE id = ?", (person_id,))
    await db.commit()


# ── 얼굴 조회/교정 ────────────────────────────────────────────────────


@router.get("/people/{person_id}/faces")
async def list_person_faces(
    person_id: int,
    source: str = Query(default="all", pattern="^(all|labeled|matched)$"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    max_score: Optional[float] = Query(default=None, ge=0.0, le=1.0),
    _: str = Depends(get_current_admin),
    db=Depends(get_ai_db),
):
    """인물의 얼굴 목록. labeled=사람이 확정, matched=자동 매칭(미확정).

    max_score 지정 시 matched 얼굴을 해당 점수 이하로 필터링
    (임계값 미리보기용 — 특정 % 부근부터 바로 보고 싶을 때)."""
    await _person_or_404(person_id, db)
    labeled_sql = """
        SELECT f.id AS face_id, f.photo_path, f.det_score,
               'labeled' AS source, NULL AS score
        FROM face_labels fl JOIN faces f ON f.id = fl.face_id
        WHERE fl.person_id = ?"""
    matched_sql = """
        SELECT f.id AS face_id, f.photo_path, f.det_score,
               'matched' AS source, fm.score AS score
        FROM face_matches fm JOIN faces f ON f.id = fm.face_id
        WHERE fm.person_id = ?
          AND fm.face_id NOT IN (SELECT face_id FROM face_labels)"""
    matched_params = [person_id]
    if max_score is not None:
        matched_sql += " AND fm.score <= ?"
        matched_params.append(max_score)
    if source == "labeled":
        sql, params = labeled_sql, [person_id]
    elif source == "matched":
        sql, params = matched_sql, matched_params
    else:
        sql, params = f"{labeled_sql} UNION ALL {matched_sql}", [person_id, *matched_params]
    sql += " ORDER BY source, score DESC LIMIT ? OFFSET ?"
    async with db.execute(sql, (*params, limit, offset)) as cur:
        rows = await cur.fetchall()
    return {"faces": [dict(r) for r in rows]}


@router.get("/people/{person_id}/photos")
async def list_person_photos(
    person_id: int,
    source: str = Query(default="all", pattern="^(all|labeled)$"),
    _: str = Depends(get_current_admin), db=Depends(get_ai_db)
):
    """인물이 등장하는 사진 경로 목록 (라벨 우선 + 매칭, source=labeled면 확정만). 앨범 생성용."""
    await _person_or_404(person_id, db)
    return {"photos": await _person_photo_paths(person_id, db, labeled_only=source == "labeled")}


@router.get("/people/{person_id}/photos-detail", response_model=SharePhotosResponse)
async def list_person_photos_detail(
    person_id: int,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=500),
    source: str = Query(default="all", pattern="^(all|labeled)$"),
    _: str = Depends(get_current_admin),
    db=Depends(get_ai_db),
    app_db=Depends(get_db),
):
    """인물 사진 상세 목록 (EXIF·URL 포함, 페이지네이션) — Admin 슬라이드쇼/전체 사진용.

    source=labeled면 확정(라벨) 얼굴이 있는 사진만, 기본(all)은 확정+추정."""
    await _person_or_404(person_id, db)
    labeled_only = source == "labeled"
    if labeled_only:
        count_sql = f"SELECT COUNT(DISTINCT f.photo_path) AS total {_PERSON_PHOTOS_LABELED_FROM}"
        count_params: tuple = (person_id,)
    else:
        count_sql = f"SELECT COUNT(DISTINCT f.photo_path) AS total {_PERSON_PHOTOS_FROM}"
        count_params = (person_id, person_id)
    async with db.execute(count_sql, count_params) as cur:
        total = (await cur.fetchone())["total"]

    offset = (page - 1) * size
    paths = await _person_photo_paths(
        person_id, db, limit=size, offset=offset, labeled_only=labeled_only
    )

    meta_map = await load_photo_meta(paths, app_db)
    photos = [
        build_share_photo_item(
            id=offset + i,
            file_path=p,
            url=f"/api/admin/photo?path={quote(p)}",
            thumb_small_url=f"/api/admin/thumb?path={quote(p)}&size=small",
            thumb_medium_url=f"/api/admin/thumb?path={quote(p)}&size=medium",
            meta=meta_map.get(p, {}),
            include_file_path=True,  # Admin 전용 — 프론트 정렬·라이트박스용
        )
        for i, p in enumerate(paths)
    ]
    return SharePhotosResponse(photos=photos, total=total, page=page)


@router.post("/people/{person_id}/confirm-matched")
async def confirm_matched_by_score(
    person_id: int, body: ConfirmByScore,
    _: str = Depends(get_current_admin), db=Depends(get_ai_db),
):
    """이 인물의 추정 얼굴 중 score >= min_score 전체를 확정 처리 (페이지네이션 무관)."""
    await _person_or_404(person_id, db)
    async with db.execute(
        """SELECT face_id FROM face_matches
           WHERE person_id = ? AND score >= ?
             AND face_id NOT IN (SELECT face_id FROM face_labels)""",
        (person_id, body.min_score),
    ) as cur:
        face_ids = [r["face_id"] for r in await cur.fetchall()]
    if face_ids:
        await db.executemany(
            "INSERT INTO face_labels (face_id, person_id) VALUES (?, ?)",
            [(fid, person_id) for fid in face_ids],
        )
        await db.commit()
    return {"count": len(face_ids)}


@router.get("/faces/unassigned")
async def list_unassigned_faces(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: str = Depends(get_current_admin),
    db=Depends(get_ai_db),
):
    """라벨도 매칭도 없는 얼굴 (인물 지정 대기). 검출 신뢰도 순."""
    async with db.execute(
        """
        SELECT f.id AS face_id, f.photo_path, f.det_score
        FROM faces f
        LEFT JOIN face_labels fl ON fl.face_id = f.id
        LEFT JOIN face_matches fm ON fm.face_id = f.id
        WHERE fl.face_id IS NULL AND fm.face_id IS NULL
        ORDER BY f.det_score DESC LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ) as cur:
        rows = await cur.fetchall()
    return {"faces": [dict(r) for r in rows]}


@router.get("/faces/ignored")
async def list_ignored_faces(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: str = Depends(get_current_admin),
    db=Depends(get_ai_db),
):
    """'등록 인물 아님'으로 무시 처리된 얼굴 (person_id IS NULL 라벨). 최근 무시 순."""
    async with db.execute(
        """
        SELECT f.id AS face_id, f.photo_path, f.det_score, fl.labeled_at
        FROM face_labels fl JOIN faces f ON f.id = fl.face_id
        WHERE fl.person_id IS NULL
        ORDER BY fl.labeled_at DESC, f.id DESC LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ) as cur:
        rows = await cur.fetchall()
    return {"faces": [dict(r) for r in rows]}


@router.get("/faces/{face_id}/similar")
async def similar_faces(
    face_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    _: str = Depends(get_current_admin),
    db=Depends(get_ai_db),
):
    """face_id와 임베딩이 비슷한 미분류 얼굴을 유사도순으로 반환 (신규 인물 탐색용).
    임베딩 벡터 계산 방식은 ai_worker/matcher.py와 동일 로직을 backend에 복제
    (컨테이너가 분리되어 코드를 공유할 수 없음 — ai.db 스키마 복제와 같은 이유)."""
    async with db.execute("SELECT embedding FROM faces WHERE id = ?", (face_id,)) as cur:
        seed_row = await cur.fetchone()
    if seed_row is None:
        raise HTTPException(status_code=404, detail="Face not found")
    seed = np.frombuffer(seed_row["embedding"], dtype=np.float32)
    seed_norm = np.linalg.norm(seed)
    if seed_norm == 0:
        return {"faces": []}
    seed = seed / seed_norm

    # 기준 얼굴 자신도 결과에 포함(유사도 1.0로 최상단) — 재정렬 화면에서 그대로 선택 가능하게.
    async with db.execute(
        """SELECT f.id, f.photo_path, f.embedding
           FROM faces f
           LEFT JOIN face_labels fl ON fl.face_id = f.id
           LEFT JOIN face_matches fm ON fm.face_id = f.id
           WHERE (fl.face_id IS NULL AND fm.face_id IS NULL) OR f.id = ?""",
        (face_id,),
    ) as cur:
        rows = await cur.fetchall()
    if not rows:
        return {"faces": []}

    mat = np.stack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    scores = (mat / norms) @ seed

    order = np.argsort(-scores)[:limit]
    return {"faces": [
        {"face_id": rows[i]["id"], "photo_path": rows[i]["photo_path"], "score": float(scores[i])}
        for i in order
    ]}


@router.post("/faces/{face_id}/label")
async def set_face_label(
    face_id: int, body: FaceLabelSet,
    _: str = Depends(get_current_admin), db=Depends(get_ai_db),
):
    """얼굴에 인물 확정 라벨 기록. person_id=null은 '등록 인물 아님(무시)'."""
    async with db.execute("SELECT id FROM faces WHERE id = ?", (face_id,)) as cur:
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Face not found")
    if body.person_id is not None:
        await _person_or_404(body.person_id, db)
    await db.execute(
        """INSERT INTO face_labels (face_id, person_id) VALUES (?, ?)
           ON CONFLICT(face_id) DO UPDATE SET
             person_id=excluded.person_id, labeled_at=CURRENT_TIMESTAMP""",
        (face_id, body.person_id),
    )
    await db.commit()
    return {"face_id": face_id, "person_id": body.person_id}


@router.post("/faces/batch-label")
async def batch_label_faces(
    body: BatchFaceLabel, _: str = Depends(get_current_admin), db=Depends(get_ai_db)
):
    """여러 얼굴을 한 번에 확정/무시 처리 (추정 얼굴 일괄 확정 UI용)."""
    if not body.face_ids:
        raise HTTPException(status_code=400, detail="face_ids가 비어 있습니다")
    if body.person_id is not None:
        await _person_or_404(body.person_id, db)
    ids = list(dict.fromkeys(body.face_ids))  # 중복 제거, 순서 유지
    placeholders = ",".join("?" * len(ids))
    async with db.execute(
        f"SELECT COUNT(*) AS n FROM faces WHERE id IN ({placeholders})", ids
    ) as cur:
        found = (await cur.fetchone())["n"]
    if found != len(ids):
        raise HTTPException(status_code=404, detail="존재하지 않는 얼굴이 포함되어 있습니다")
    await db.executemany(
        """INSERT INTO face_labels (face_id, person_id) VALUES (?, ?)
           ON CONFLICT(face_id) DO UPDATE SET
             person_id=excluded.person_id, labeled_at=CURRENT_TIMESTAMP""",
        [(fid, body.person_id) for fid in ids],
    )
    await db.commit()
    return {"count": len(ids)}


@router.delete("/faces/{face_id}/label", status_code=204)
async def delete_face_label(
    face_id: int, _: str = Depends(get_current_admin), db=Depends(get_ai_db)
):
    await db.execute("DELETE FROM face_labels WHERE face_id = ?", (face_id,))
    await db.commit()


@router.delete("/faces/batch-unlabel", status_code=204)
async def batch_unlabel_faces(
    body: BatchFaceUnlabel, _: str = Depends(get_current_admin), db=Depends(get_ai_db)
):
    """여러 얼굴의 라벨을 한 번에 삭제 (무시 해제/확정 취소 일괄 처리용)."""
    if not body.face_ids:
        raise HTTPException(status_code=400, detail="face_ids가 비어 있습니다")
    ids = list(dict.fromkeys(body.face_ids))
    placeholders = ",".join("?" * len(ids))
    await db.execute(f"DELETE FROM face_labels WHERE face_id IN ({placeholders})", ids)
    await db.commit()


@router.get("/faces/{face_id}/crop")
async def face_crop(face_id: int, _: str = Depends(_admin_image_auth)):
    """워커가 저장한 얼굴 크롭 썸네일 서빙 (Bearer 또는 admin_img_session 쿠키)."""
    path = os.path.join(faces_dir(), f"{face_id}.jpg")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Crop not found")
    return FileResponse(path, media_type="image/jpeg")


# ── AI 워커 상태/트리거 ───────────────────────────────────────────────


@router.get("/ai/status")
async def ai_status(_: str = Depends(get_current_admin), db=Depends(get_ai_db)):
    async with db.execute(
        """SELECT
             (SELECT COUNT(*) FROM photos_analyzed) AS photos,
             (SELECT COUNT(*) FROM photos_analyzed WHERE status='error') AS errors,
             (SELECT COUNT(*) FROM faces) AS faces,
             (SELECT COUNT(*) FROM persons) AS persons,
             (SELECT COUNT(*) FROM face_labels) AS labels"""
    ) as cur:
        stats = dict(await cur.fetchone())
    async with db.execute(
        "SELECT id, type, status, requested_at, finished_at FROM jobs ORDER BY id DESC LIMIT 5"
    ) as cur:
        stats["recent_jobs"] = [dict(r) for r in await cur.fetchall()]
    return stats


@router.post("/ai/jobs", status_code=201)
async def create_job(
    body: JobCreate, _: str = Depends(get_current_admin), db=Depends(get_ai_db)
):
    if body.type not in _JOB_TYPES:
        raise HTTPException(status_code=400, detail=f"type은 {_JOB_TYPES} 중 하나")
    # 같은 타입의 대기/실행 중 잡이 있으면 중복 생성하지 않음
    async with db.execute(
        "SELECT id FROM jobs WHERE type = ? AND status IN ('pending','running')",
        (body.type,),
    ) as cur:
        existing = await cur.fetchone()
    if existing:
        return {"id": existing["id"], "type": body.type, "duplicated": True}
    cur = await db.execute("INSERT INTO jobs (type) VALUES (?)", (body.type,))
    await db.commit()
    return {"id": cur.lastrowid, "type": body.type, "duplicated": False}


@router.get("/ai/settings")
async def get_ai_settings(_: str = Depends(get_current_admin), db=Depends(get_ai_db)):
    """scan_hour: Admin이 설정한 야간 스캔 시각. null이면 워커 환경변수(AI_SCAN_HOUR) 사용."""
    async with db.execute(
        "SELECT value FROM ai_settings WHERE key = 'scan_hour'"
    ) as cur:
        row = await cur.fetchone()
    return {"scan_hour": int(row["value"]) if row else None}


@router.patch("/ai/settings")
async def update_ai_settings(
    body: AiSettingsUpdate, _: str = Depends(get_current_admin), db=Depends(get_ai_db)
):
    await db.execute(
        "INSERT OR REPLACE INTO ai_settings (key, value) VALUES ('scan_hour', ?)",
        (str(body.scan_hour),),
    )
    await db.commit()
    return {"scan_hour": body.scan_hour}
