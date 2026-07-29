"""Phase 2 인물(People) 관리 API — ai.db 기반.

쓰기 대상: persons, face_labels, jobs, ai_settings (그 외 테이블은 AI 워커가 씀).
유효 인물 판정: face_labels가 있으면 그 값이 우선, 없으면 face_matches.
"""

import asyncio
import os
import secrets
import sqlite3
import time
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
    PersonCoverSet,
    PersonCreate,
    SharePhotosResponse,
    build_share_photo_item,
    build_slideshow_defaults,
)
from backend.services.auth import admin_image_auth, get_current_admin
from backend.services.paths import build_filename_index
from backend.services.photo_meta import load_photo_meta
from backend.services.settings import get_settings

router = APIRouter(prefix="/api/admin", tags=["admin-people"])

_JOB_TYPES = {"scan", "rematch", "review_ignored"}

# photos-detail 페이지네이션 스냅샷: 최초 요청(page=1, snapshot 미지정)에서 계산한
# 전체 photo_path 순서를 토큰에 고정해두고 이후 페이지 요청은 이 목록만 슬라이스한다.
# 슬라이드쇼 재생 중 다른 곳에서 라벨/매칭이 바뀌어도 이미 시작된 세션의 페이지
# 순서·개수가 흔들리지 않도록 하기 위함 (OFFSET 기반 재계산 시 밀림 발생 가능).
_PERSON_PHOTOS_SNAPSHOT_TTL = 1800  # 초
# 토큰 -> (person_id, labeled_only, photo_paths, 만료시각). person_id/labeled_only를
# 함께 저장해 토큰이 발급된 (인물, source) 조합에서만 유효하도록 검증한다.
_person_photos_snapshots: dict[str, tuple[int, bool, list[str], float]] = {}


def _evict_stale_person_photos_snapshots() -> None:
    now = time.time()
    stale = [k for k, v in _person_photos_snapshots.items() if now >= v[3]]
    for k in stale:
        del _person_photos_snapshots[k]
    if len(_person_photos_snapshots) > 200:
        oldest = min(_person_photos_snapshots, key=lambda k: _person_photos_snapshots[k][3])
        del _person_photos_snapshots[oldest]


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
               COALESCE(
                 (SELECT fl.face_id FROM face_labels fl
                   WHERE fl.face_id = p.cover_face_id AND fl.person_id = p.id),
                 (SELECT fl.face_id FROM face_labels fl
                   WHERE fl.person_id = p.id ORDER BY fl.labeled_at LIMIT 1)
               ) AS cover_face_id
        FROM persons p ORDER BY labeled_count + matched_count DESC, p.name
        """
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ── 경로 복구 ─────────────────────────────────────────────────────────
#
# photos_analyzed/faces는 원래 AI 워커 전용 쓰기 테이블이다(파일 상단 주석 참조).
# rename/move 후보는 이 스캔 엔드포인트와 ai_worker/scanner.py(야간 자동 스캔)
# 양쪽이 pending_path_repairs에 제안만 쌓는다 — 실제 UPDATE는 admin이 아래
# path-repairs 승인 엔드포인트를 호출해야만 일어난다. 그 승인 엔드포인트가
# 예외적으로 LumisShow가 photos_analyzed.path/faces.photo_path를 직접 UPDATE하는
# 지점이다 — on-demand·저빈도 관리자 액션이라 WAL+busy_timeout(15s)으로 워커와의
# 동시 쓰기가 안전하게 직렬화된다. face_labels/face_matches는 FK(face_id)라
# 건드리지 않아도 라벨이 그대로 유지된다.


@router.post("/people/repair-paths")
async def repair_people_paths(
    _: str = Depends(get_current_admin), db=Depends(get_ai_db)
):
    """실제 파일이 없는(orphan) photos_analyzed 경로를 파일명 기반으로 스캔.
    후보가 1개(유일 매칭)면 pending_path_repairs에 rename 승인 대기로 제안(proposed).
    2개 이상(ambiguous)이면 보고만 한다(admin_albums의 repair_album_paths와 동일
    패턴, 자동 삭제 없음). 0개(not_found) — 진짜로 파일이 사라진 경우 —는
    pending_orphan_cleanups에 삭제 승인 대기로도 함께 쌓는다. 실제 반영은 admin이
    /people/path-repairs/{id}/approve(-all) 또는
    /people/orphan-cleanups/{id}/approve(-all)로 승인해야 일어난다."""
    photo_root = os.path.realpath(os.getenv("PHOTO_ROOT", "./testdata/photos"))

    async with db.execute("SELECT path FROM photos_analyzed") as cur:
        all_paths = [row["path"] for row in await cur.fetchall()]
    analyzed_set = set(all_paths)

    broken = [p for p in all_paths if not os.path.isfile(os.path.join(photo_root, p))]
    total_checked = len(all_paths)

    if not broken:
        return {"total_checked": total_checked, "proposed": [], "ambiguous": [], "not_found": []}

    index = await asyncio.to_thread(build_filename_index, photo_root)

    proposed, ambiguous, not_found = [], [], []

    # basename별로 묶는다 — orphan 쪽도 동명(카메라 IMG_0001.jpg류)이 2개 이상이면
    # 어느 old_path를 새 경로에 매칭해야 할지 알 수 없어 ambiguous로 남겨야 한다.
    broken_by_basename: dict[str, list[str]] = {}
    for p in broken:
        broken_by_basename.setdefault(os.path.basename(p).lower(), []).append(p)

    for basename, old_paths in broken_by_basename.items():
        # 이미 photos_analyzed에 등록된 경로는 후보에서 제외 — 아니면 승인 시
        # path(PRIMARY KEY) 중복으로 충돌한다.
        candidates = [c for c in index.get(basename, []) if c not in analyzed_set]

        if not candidates:
            not_found.extend(old_paths)
            for old_path in old_paths:
                await db.execute(
                    "INSERT OR IGNORE INTO pending_orphan_cleanups (path, source) "
                    "VALUES (?, 'manual')",
                    (old_path,),
                )
            continue
        if len(old_paths) > 1 or len(candidates) > 1:
            for old_path in old_paths:
                ambiguous.append({"old_path": old_path, "candidates": sorted(candidates)})
            continue

        old_path, new_path = old_paths[0], candidates[0]
        cur = await db.execute(
            "INSERT OR IGNORE INTO pending_path_repairs (old_path, new_path, source) "
            "VALUES (?, ?, 'manual')",
            (old_path, new_path),
        )
        if cur.rowcount:
            proposed.append({"id": cur.lastrowid, "old_path": old_path, "new_path": new_path})
        else:
            # old_path UNIQUE 충돌 — 이미 대기 중인 제안이 있다는 뜻(rejected는 더 이상
            # row로 남지 않으므로 pending만 가능). 재실행에서도 응답에 포함해 admin이
            # "못 찾았다"로 오해하지 않게 한다. new_path는 최근 재계산 값이 아니라
            # 실제로 대기 중인 값을 반환한다.
            async with db.execute(
                "SELECT id, new_path FROM pending_path_repairs WHERE old_path = ? AND status = 'pending'",
                (old_path,),
            ) as existing_cur:
                existing = await existing_cur.fetchone()
            if existing:
                proposed.append(
                    {"id": existing["id"], "old_path": old_path, "new_path": existing["new_path"]}
                )

    await db.commit()
    return {
        "total_checked": total_checked,
        "proposed": proposed,
        "ambiguous": ambiguous,
        "not_found": not_found,
    }


async def _apply_path_repair(db, photo_root: str, old_path: str, new_path: str) -> None:
    """photos_analyzed.path/faces.photo_path를 new_path로 갱신(face_id 유지).
    new_path가 이미 photos_analyzed에 있으면(레이스) sqlite3.IntegrityError."""
    try:
        new_mtime = os.path.getmtime(os.path.join(photo_root, new_path))
    except OSError:
        new_mtime = None
    if new_mtime is not None:
        await db.execute(
            "UPDATE photos_analyzed SET path = ?, mtime = ? WHERE path = ?",
            (new_path, new_mtime, old_path),
        )
    else:
        await db.execute(
            "UPDATE photos_analyzed SET path = ? WHERE path = ?",
            (new_path, old_path),
        )
    await db.execute(
        "UPDATE faces SET photo_path = ? WHERE photo_path = ?",
        (new_path, old_path),
    )


@router.get("/people/path-repairs")
async def list_path_repairs(
    _: str = Depends(get_current_admin), db=Depends(get_ai_db)
):
    """승인 대기 중(pending) 경로 복구 제안 목록."""
    async with db.execute(
        "SELECT id, old_path, new_path, source, detected_at FROM pending_path_repairs "
        "WHERE status = 'pending' ORDER BY detected_at"
    ) as cur:
        rows = await cur.fetchall()
    return {"repairs": [dict(r) for r in rows]}


@router.post("/people/path-repairs/{repair_id}/approve")
async def approve_path_repair(
    repair_id: int, _: str = Depends(get_current_admin), db=Depends(get_ai_db)
):
    """제안 1건을 승인 — photos_analyzed/faces를 new_path로 UPDATE하고 제안을 삭제."""
    photo_root = os.path.realpath(os.getenv("PHOTO_ROOT", "./testdata/photos"))
    async with db.execute(
        "SELECT old_path, new_path FROM pending_path_repairs WHERE id = ? AND status = 'pending'",
        (repair_id,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="대기 중인 제안을 찾을 수 없습니다")

    try:
        await _apply_path_repair(db, photo_root, row["old_path"], row["new_path"])
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail=f"{row['new_path']}가 이미 분석된 경로입니다 — 제안을 거부해 주세요",
        )
    await db.execute("DELETE FROM pending_path_repairs WHERE id = ?", (repair_id,))
    await db.commit()
    return {"old_path": row["old_path"], "new_path": row["new_path"]}


@router.post("/people/path-repairs/{repair_id}/reject")
async def reject_path_repair(
    repair_id: int, _: str = Depends(get_current_admin), db=Depends(get_ai_db)
):
    """제안 1건을 무시(dismiss) — row 자체를 삭제해 적용하지 않는다. status를
    'rejected'로 영구 고정하면 old_path UNIQUE 제약 때문에 다음 스캔이 같은 rename을
    재제안할 수 없고, 그 사이 new_path가 일반 스캔으로 별개 사진으로 분석돼버리면
    영영 되돌릴 수 없었다(승인 시도해도 409). row를 지우면 다음 스캔에서 조건이
    같으면(둘 다 아직 미확정) 다시 제안되거나, new_path가 이미 분석돼버렸으면
    old_path는 not_found로 재분류돼 orphan-cleanup 제안으로 넘어간다."""
    cur = await db.execute(
        "DELETE FROM pending_path_repairs WHERE id = ? AND status = 'pending'",
        (repair_id,),
    )
    await db.commit()
    if not cur.rowcount:
        raise HTTPException(status_code=404, detail="대기 중인 제안을 찾을 수 없습니다")
    return {"id": repair_id, "status": "dismissed"}


@router.post("/people/path-repairs/approve-all")
async def approve_all_path_repairs(
    _: str = Depends(get_current_admin), db=Depends(get_ai_db)
):
    """대기 중인 제안 전체를 순회 승인."""
    photo_root = os.path.realpath(os.getenv("PHOTO_ROOT", "./testdata/photos"))
    async with db.execute(
        "SELECT id, old_path, new_path FROM pending_path_repairs WHERE status = 'pending'"
    ) as cur:
        rows = await cur.fetchall()

    applied, failed = [], []
    for row in rows:
        try:
            await _apply_path_repair(db, photo_root, row["old_path"], row["new_path"])
        except sqlite3.IntegrityError:
            failed.append({"old_path": row["old_path"], "new_path": row["new_path"]})
            continue
        await db.execute("DELETE FROM pending_path_repairs WHERE id = ?", (row["id"],))
        applied.append({"old_path": row["old_path"], "new_path": row["new_path"]})

    await db.commit()
    return {"applied": applied, "failed": failed}


# ── 완전 삭제(orphan) 정리 ────────────────────────────────────────────
#
# rename 후보를 찾지 못해 pending_orphan_cleanups에 쌓인 경로 — 파일이 진짜로
# 없어졌다고 admin이 승인해야만 photos_analyzed/faces(ai.db)와 photo_meta_cache
# (app.db, EXIF 캐시)를 함께 삭제한다. faces 삭제는 FK CASCADE로 face_labels/
# face_matches까지 함께 지운다 — 즉 이 인물에게 연결된 라벨도 함께 사라진다
# (파일이 실제로 없으므로 되돌릴 수 없는 삭제).


async def _apply_orphan_cleanup(db, app_db, path: str) -> None:
    """path의 photos_analyzed/faces(ai.db) 행을 삭제하고, photo_meta_cache(app.db)에
    같은 경로 캐시가 있으면 함께 삭제한다(없어도 무방 — best-effort)."""
    await db.execute("DELETE FROM faces WHERE photo_path = ?", (path,))
    await db.execute("DELETE FROM photos_analyzed WHERE path = ?", (path,))
    await app_db.execute("DELETE FROM photo_meta_cache WHERE file_path = ?", (path,))
    await app_db.commit()


@router.get("/people/orphan-cleanups")
async def list_orphan_cleanups(
    _: str = Depends(get_current_admin), db=Depends(get_ai_db)
):
    """승인 대기 중(pending) 완전 삭제 제안 목록."""
    async with db.execute(
        "SELECT id, path, source, detected_at FROM pending_orphan_cleanups "
        "WHERE status = 'pending' ORDER BY detected_at"
    ) as cur:
        rows = await cur.fetchall()
    return {"cleanups": [dict(r) for r in rows]}


@router.post("/people/orphan-cleanups/{cleanup_id}/approve")
async def approve_orphan_cleanup(
    cleanup_id: int, _: str = Depends(get_current_admin),
    db=Depends(get_ai_db), app_db=Depends(get_db),
):
    """제안 1건을 승인 — 파일이 여전히 없는지 재확인 후 삭제하고 제안을 지운다."""
    photo_root = os.path.realpath(os.getenv("PHOTO_ROOT", "./testdata/photos"))
    async with db.execute(
        "SELECT path FROM pending_orphan_cleanups WHERE id = ? AND status = 'pending'",
        (cleanup_id,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="대기 중인 제안을 찾을 수 없습니다")

    path = row["path"]
    if os.path.isfile(os.path.join(photo_root, path)):
        raise HTTPException(
            status_code=409,
            detail=f"{path} 파일이 다시 존재합니다 — 제안을 거부하고 다시 스캔해 주세요",
        )

    await _apply_orphan_cleanup(db, app_db, path)
    await db.execute("DELETE FROM pending_orphan_cleanups WHERE id = ?", (cleanup_id,))
    await db.commit()
    return {"path": path}


@router.post("/people/orphan-cleanups/{cleanup_id}/reject")
async def reject_orphan_cleanup(
    cleanup_id: int, _: str = Depends(get_current_admin), db=Depends(get_ai_db)
):
    """제안 1건을 거부 — status만 'rejected'로 바꿔 재제안을 막는다(삭제 없음)."""
    cur = await db.execute(
        "UPDATE pending_orphan_cleanups SET status = 'rejected' WHERE id = ? AND status = 'pending'",
        (cleanup_id,),
    )
    await db.commit()
    if not cur.rowcount:
        raise HTTPException(status_code=404, detail="대기 중인 제안을 찾을 수 없습니다")
    return {"id": cleanup_id, "status": "rejected"}


@router.post("/people/orphan-cleanups/approve-all")
async def approve_all_orphan_cleanups(
    _: str = Depends(get_current_admin), db=Depends(get_ai_db), app_db=Depends(get_db),
):
    """대기 중인 제안 전체를 순회 승인 — 그 사이 파일이 다시 생긴 건 건너뛴다."""
    photo_root = os.path.realpath(os.getenv("PHOTO_ROOT", "./testdata/photos"))
    async with db.execute(
        "SELECT id, path FROM pending_orphan_cleanups WHERE status = 'pending'"
    ) as cur:
        rows = await cur.fetchall()

    applied, skipped = [], []
    for row in rows:
        if os.path.isfile(os.path.join(photo_root, row["path"])):
            skipped.append(row["path"])
            continue
        await _apply_orphan_cleanup(db, app_db, row["path"])
        await db.execute("DELETE FROM pending_orphan_cleanups WHERE id = ?", (row["id"],))
        applied.append(row["path"])

    await db.commit()
    return {"applied": applied, "skipped": skipped}


@router.get("/people/{person_id}")
async def get_person(
    person_id: int, _: str = Depends(get_current_admin), db=Depends(get_ai_db)
):
    async with db.execute(
        """
        SELECT p.id, p.name, p.created_at,
               (SELECT COUNT(*) FROM face_labels fl
                 WHERE fl.person_id = p.id) AS labeled_count,
               (SELECT COUNT(*) FROM face_matches fm
                 WHERE fm.person_id = p.id
                   AND fm.face_id NOT IN (SELECT face_id FROM face_labels)) AS matched_count,
               COALESCE(
                 (SELECT fl.face_id FROM face_labels fl
                   WHERE fl.face_id = p.cover_face_id AND fl.person_id = p.id),
                 (SELECT fl.face_id FROM face_labels fl
                   WHERE fl.person_id = p.id ORDER BY fl.labeled_at LIMIT 1)
               ) AS cover_face_id
        FROM persons p WHERE p.id = ?
        """,
        (person_id,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return dict(row)


@router.post("/people", status_code=201)
async def create_person(
    body: PersonCreate, _: str = Depends(get_current_admin), db=Depends(get_ai_db)
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="이름을 입력하세요")
    # DB의 UNIQUE 인덱스가 (기존 중복 데이터로 인해) 생성되지 못했을 가능성에 대비한
    # 애플리케이션 레벨 방어 — 정상 케이스는 UNIQUE 인덱스가 원자적으로 막아준다.
    async with db.execute("SELECT id FROM persons WHERE name = ?", (name,)) as cur:
        if await cur.fetchone() is not None:
            raise HTTPException(status_code=400, detail="이미 존재하는 인물입니다")
    try:
        cur = await db.execute("INSERT INTO persons (name) VALUES (?)", (name,))
        await db.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="이미 존재하는 인물입니다")
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
    async with db.execute(
        "SELECT id FROM persons WHERE name = ? AND id != ?", (name, person_id)
    ) as cur:
        if await cur.fetchone() is not None:
            raise HTTPException(status_code=400, detail="이미 존재하는 인물입니다")
    try:
        await db.execute("UPDATE persons SET name = ? WHERE id = ?", (name, person_id))
        await db.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="이미 존재하는 인물입니다")
    return {"id": person_id, "name": name}


@router.put("/people/{person_id}/cover")
async def set_person_cover(
    person_id: int, body: PersonCoverSet,
    _: str = Depends(get_current_admin), db=Depends(get_ai_db),
):
    """인물 커버를 확정 얼굴 중 하나로 지정. face_id=None이면 자동(가장 먼저
    확정된 얼굴)으로 되돌린다. 지정한 face_id는 이 인물의 확정(face_labels) 얼굴
    이어야 한다 — 그래야 커버 조회 SQL(COALESCE)의 유효성 검사와 일치한다."""
    await _person_or_404(person_id, db)
    if body.face_id is not None:
        async with db.execute(
            "SELECT 1 FROM face_labels WHERE face_id = ? AND person_id = ?",
            (body.face_id, person_id),
        ) as cur:
            if await cur.fetchone() is None:
                raise HTTPException(status_code=400, detail="해당 인물의 확정 얼굴이 아닙니다")
    await db.execute(
        "UPDATE persons SET cover_face_id = ? WHERE id = ?", (body.face_id, person_id)
    )
    await db.commit()
    return {"id": person_id, "cover_face_id": body.face_id}


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
    snapshot: Optional[str] = Query(default=None),
    _: str = Depends(get_current_admin),
    db=Depends(get_ai_db),
    app_db=Depends(get_db),
):
    """인물 사진 상세 목록 (EXIF·URL 포함, 페이지네이션) — Admin 슬라이드쇼/전체 사진용.

    source=labeled면 확정(라벨) 얼굴이 있는 사진만, 기본(all)은 확정+추정.

    snapshot 미지정(최초 요청) 시 전체 photo_path 순서를 계산해 토큰에 고정하고
    응답에 실어 보낸다. 이후 요청이 같은 snapshot을 넘기면 그 고정 목록만 슬라이스한다
    (라벨/매칭이 재생 중 바뀌어도 이미 시작된 세션의 페이지가 밀리지 않도록)."""
    await _person_or_404(person_id, db)
    labeled_only = source == "labeled"

    _evict_stale_person_photos_snapshots()
    cached = _person_photos_snapshots.get(snapshot) if snapshot else None
    # 캐시된 토큰이 다른 인물/source로 발급된 것이면(URL 재사용 등) 무시하고 새로 계산 —
    # 토큰이 자신이 속한 (person_id, source) 조합에서만 유효하도록 보장.
    if cached and cached[0] == person_id and cached[1] == labeled_only:
        all_paths = cached[2]
    else:
        all_paths = await _person_photo_paths(person_id, db, labeled_only=labeled_only)
        snapshot = secrets.token_hex(8)
        _person_photos_snapshots[snapshot] = (person_id, labeled_only, all_paths, time.time() + _PERSON_PHOTOS_SNAPSHOT_TTL)

    total = len(all_paths)
    offset = (page - 1) * size
    paths = all_paths[offset: offset + size]

    meta_map = await load_photo_meta(paths, app_db)
    photos = [
        build_share_photo_item(
            id=offset + i,
            file_path=p,
            url=f"/api/admin/photo?path={quote(p)}",
            thumb_small_url=f"/api/admin/thumb?path={quote(p)}&size=small",
            thumb_medium_url=f"/api/admin/thumb?path={quote(p)}&size=medium",
            thumb_large_url=f"/api/admin/thumb?path={quote(p)}&size=large",
            meta=meta_map.get(p, {}),
            include_file_path=True,  # Admin 전용 — 프론트 정렬·라이트박스용
        )
        for i, p in enumerate(paths)
    ]
    return SharePhotosResponse(photos=photos, total=total, page=page, snapshot=snapshot)


@router.get("/people/{person_id}/slideshow-meta")
async def person_slideshow_meta(
    person_id: int,
    _: str = Depends(get_current_admin),
    db=Depends(get_ai_db),
    app_db=Depends(get_db),
):
    """인물 슬라이드쇼 진입 화면(loadAlbum)용 메타 — 인물에는 앨범이 없으므로 전역
    설정만 적용하고 음악은 항상 없음(False) 고정. share.py get_album()과 동일한
    build_slideshow_defaults()를 사용해 필드 매핑·폴백 규칙을 공유한다."""
    await _person_or_404(person_id, db)
    sv = await get_settings(app_db)
    return {
        "music_count": 0,
        "music_names": [],
        "slideshow_defaults": build_slideshow_defaults({"music": False}, sv),
    }


@router.delete("/people/{person_id}/photo-label", status_code=204)
async def unlabel_person_photo(
    person_id: int, path: str = Query(...),
    _: str = Depends(get_current_admin), db=Depends(get_ai_db),
):
    """이 인물의 확정 라벨 중 해당 사진 경로에 속한 것을 모두 해제 (전체 사진 라이트박스 '확정 해제' 버튼용)."""
    await _person_or_404(person_id, db)
    async with db.execute(
        """SELECT fl.face_id FROM face_labels fl JOIN faces f ON f.id = fl.face_id
           WHERE fl.person_id = ? AND f.photo_path = ?""",
        (person_id, path),
    ) as cur:
        face_ids = [r["face_id"] for r in await cur.fetchall()]
    if face_ids:
        placeholders = ",".join("?" * len(face_ids))
        await db.execute(f"DELETE FROM face_labels WHERE face_id IN ({placeholders})", face_ids)
        await db.commit()


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


@router.get("/people/{person_id}/ignored-candidates")
async def list_ignored_review_candidates(
    person_id: int, _: str = Depends(get_current_admin), db=Depends(get_ai_db)
):
    """review_ignored 잡이 찾아낸, 이 인물일 가능성이 있는 '무시' 얼굴 후보.
    이미 확정/재무시 등으로 라벨이 바뀐 얼굴은 자동으로 제외(face_labels 조인 필터)."""
    await _person_or_404(person_id, db)
    async with db.execute(
        """SELECT irc.face_id, f.photo_path, irc.score
           FROM ignored_review_candidates irc
           JOIN faces f ON f.id = irc.face_id
           LEFT JOIN face_labels fl ON fl.face_id = irc.face_id
           WHERE irc.person_id = ?
             AND (fl.face_id IS NULL OR fl.person_id IS NULL)
           ORDER BY irc.score DESC""",
        (person_id,),
    ) as cur:
        rows = await cur.fetchall()
    # '마지막 재검토' 시각은 후보 테이블이 아니라 jobs.finished_at에서 가져온다 —
    # 후보가 0건으로 끝난 재검토는 ignored_review_candidates에 행을 남기지 않으므로
    # 그 경우와 '한 번도 검토한 적 없음'을 구분할 수 있는 유일한 소스.
    async with db.execute(
        """SELECT finished_at FROM jobs
           WHERE type = 'review_ignored' AND target_person_id = ? AND status = 'done'
           ORDER BY finished_at DESC LIMIT 1""",
        (person_id,),
    ) as cur:
        reviewed = await cur.fetchone()
    return {
        "candidates": [dict(r) for r in rows],
        "reviewed_at": reviewed["finished_at"] if reviewed else None,
    }


@router.get("/people/{person_id}/review-ignored-status")
async def review_ignored_status(
    person_id: int, _: str = Depends(get_current_admin), db=Depends(get_ai_db)
):
    """이 인물에 대한 가장 최근 review_ignored 잡 상태 (Admin 인물 상세 폴링용)."""
    await _person_or_404(person_id, db)
    async with db.execute(
        """SELECT id, status, requested_at, finished_at FROM jobs
           WHERE type = 'review_ignored' AND target_person_id = ?
           ORDER BY id DESC LIMIT 1""",
        (person_id,),
    ) as cur:
        row = await cur.fetchone()
    return {"job": dict(row) if row else None}


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


_SIMILAR_FACES_CANDIDATE_LIMIT = int(os.getenv("SIMILAR_FACES_CANDIDATE_LIMIT", "20000"))


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
    async with db.execute(
        "SELECT id, photo_path, embedding FROM faces WHERE id = ?", (face_id,)
    ) as cur:
        seed_row = await cur.fetchone()
    if seed_row is None:
        raise HTTPException(status_code=404, detail="Face not found")
    seed = np.frombuffer(seed_row["embedding"], dtype=np.float32)
    seed_norm = np.linalg.norm(seed)
    if seed_norm == 0:
        return {"faces": []}
    seed = seed / seed_norm

    # 미분류 얼굴이 매우 많을 경우 매 요청마다 전체를 np.stack하면 메모리 부담이 크므로
    # 후보를 SIMILAR_FACES_CANDIDATE_LIMIT로 제한 (최근 얼굴 우선).
    async with db.execute(
        """SELECT f.id, f.photo_path, f.embedding
           FROM faces f
           LEFT JOIN face_labels fl ON fl.face_id = f.id
           LEFT JOIN face_matches fm ON fm.face_id = f.id
           WHERE fl.face_id IS NULL AND fm.face_id IS NULL
           ORDER BY f.id DESC LIMIT ?""",
        (_SIMILAR_FACES_CANDIDATE_LIMIT,),
    ) as cur:
        rows = await cur.fetchall()

    # 기준 얼굴 자신도 결과에 포함(유사도 1.0로 최상단) — 재정렬 화면에서 그대로 선택 가능하게.
    # LIMIT으로 인해 후보 목록에서 밀려났을 수 있으므로 별도로 보장.
    if not any(r["id"] == face_id for r in rows):
        rows = [seed_row] + list(rows)
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


@router.post("/faces/batch-unlabel", status_code=204)
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
async def face_crop(face_id: int, _: str = Depends(admin_image_auth)):
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
             (SELECT COUNT(*) FROM face_labels) AS labels,
             (SELECT COUNT(*) FROM faces f
                LEFT JOIN face_labels fl ON fl.face_id = f.id
                LEFT JOIN face_matches fm ON fm.face_id = f.id
                WHERE fl.face_id IS NULL AND fm.face_id IS NULL) AS unassigned"""
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
    if body.type == "review_ignored":
        if body.target_person_id is None:
            raise HTTPException(status_code=400, detail="target_person_id가 필요합니다")
        await _person_or_404(body.target_person_id, db)
        # 같은 인물의 대기/실행 중 잡이 있으면 중복 생성하지 않음
        async with db.execute(
            """SELECT id FROM jobs WHERE type = ? AND target_person_id = ?
               AND status IN ('pending','running')""",
            (body.type, body.target_person_id),
        ) as cur:
            existing = await cur.fetchone()
        if existing:
            return {"id": existing["id"], "type": body.type, "duplicated": True}
        cur = await db.execute(
            "INSERT INTO jobs (type, target_person_id) VALUES (?, ?)",
            (body.type, body.target_person_id),
        )
        await db.commit()
        return {"id": cur.lastrowid, "type": body.type, "duplicated": False}

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
