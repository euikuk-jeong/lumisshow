"""Admin 태그 관리 API — ai.db photo_tags 기반 (Phase 5, doc/tagging_requirement.md
"Admin 태그 관리 화면" 절).

source='person'은 다루지 않는다 — admin_people.py가 face_labels 변경 시마다
_sync_person_tag()로 이미 전담 관리 중이라, 이 화면에서 photo_tags(source='person')를
직접 건드리면 두 화면이 서로 다른 경로로 같은 행을 써서 동기화가 깨질 위험이 있다.

source='location'은 조회만 지원한다(목록·사진 그리드는 노출하되 rename/delete는 막음) —
photo_locations가 정본이고 photo_tags는 검색용 복제본이라, 여기서 태그만 지우면
photo_locations와 어긋난다. 수동 교정은 photo_locations 전용 UI가 필요(이번 범위 아님,
doc의 "추후 UI" 항목).
"""

import sqlite3
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.models.ai_database import get_ai_db
from backend.models.database import get_db
from backend.models.schemas import (
    ManualTagCreate,
    SharePhotosResponse,
    TagRenameRequest,
    build_share_photo_item,
)
from backend.services.auth import get_current_admin
from backend.services.photo_meta import load_photo_meta
from backend.services.tag_vocab import MANUAL_TAG_VOCAB

router = APIRouter(prefix="/api/admin", tags=["admin-ai-tags"])

_VIEWABLE_SOURCES = ("ai", "manual", "path", "location")
_EDITABLE_SOURCES = {"ai", "manual", "path"}


@router.get("/tags")
async def list_tags(_: str = Depends(get_current_admin), db=Depends(get_ai_db)):
    placeholders = ",".join("?" * len(_VIEWABLE_SOURCES))
    async with db.execute(
        f"""SELECT tag, source, COUNT(*) AS count, MIN(photo_path) AS sample_path
            FROM photo_tags WHERE source IN ({placeholders})
            GROUP BY tag, source ORDER BY count DESC, tag""",
        _VIEWABLE_SOURCES,
    ) as cur:
        rows = await cur.fetchall()
    return {"tags": [dict(r) for r in rows]}


@router.get("/tags/vocab")
async def get_manual_tag_vocab(_: str = Depends(get_current_admin)):
    return {"vocab": MANUAL_TAG_VOCAB}


@router.get("/tags/{tag}/photos", response_model=SharePhotosResponse)
async def list_tag_photos(
    tag: str,
    source: str = Query(...),
    _: str = Depends(get_current_admin),
    db=Depends(get_ai_db),
    app_db=Depends(get_db),
):
    if source not in _VIEWABLE_SOURCES:
        raise HTTPException(status_code=400, detail="지원하지 않는 source입니다")
    async with db.execute(
        "SELECT photo_path FROM photo_tags WHERE tag = ? AND source = ? ORDER BY photo_path",
        (tag, source),
    ) as cur:
        paths = [r["photo_path"] for r in await cur.fetchall()]

    meta_map = await load_photo_meta(paths, app_db)
    photos = [
        build_share_photo_item(
            id=i,
            file_path=p,
            url=f"/api/admin/photo?path={quote(p)}",
            thumb_small_url=f"/api/admin/thumb?path={quote(p)}&size=small",
            thumb_medium_url=f"/api/admin/thumb?path={quote(p)}&size=medium",
            thumb_large_url=f"/api/admin/thumb?path={quote(p)}&size=large",
            meta=meta_map.get(p, {}),
            include_file_path=True,
        )
        for i, p in enumerate(paths)
    ]
    return SharePhotosResponse(photos=photos, total=len(photos), page=1)


@router.delete("/tags/{tag}/photo", status_code=204)
async def delete_tag_from_photo(
    tag: str,
    path: str = Query(...),
    source: str = Query(...),
    _: str = Depends(get_current_admin),
    db=Depends(get_ai_db),
):
    if source not in _EDITABLE_SOURCES:
        raise HTTPException(
            status_code=400, detail=f"source는 {sorted(_EDITABLE_SOURCES)} 중 하나만 삭제할 수 있습니다"
        )
    cur = await db.execute(
        "DELETE FROM photo_tags WHERE tag = ? AND photo_path = ? AND source = ?",
        (tag, path, source),
    )
    await db.commit()
    if not cur.rowcount:
        raise HTTPException(status_code=404, detail="태그를 찾을 수 없습니다")


@router.put("/tags/{tag}/rename")
async def rename_tag(
    tag: str,
    body: TagRenameRequest,
    _: str = Depends(get_current_admin),
    db=Depends(get_ai_db),
):
    """(tag, source) 조합 전체를 new_tag로 일괄 변경.

    UNIQUE(photo_path, tag, source)에 source를 포함시킨 설계 근거(서로 다른 source의
    동일 텍스트가 별개 행으로 공존해야 함, doc/tagging_requirement.md 참고)와 같은
    이유로 rename도 source 하나로 스코프를 한정한다 — 다른 source의 동일 텍스트까지
    함께 바뀌면 그 격리 의도가 깨진다."""
    if body.source not in _EDITABLE_SOURCES:
        raise HTTPException(
            status_code=400, detail=f"source는 {sorted(_EDITABLE_SOURCES)} 중 하나만 변경할 수 있습니다"
        )
    new_tag = body.new_tag.strip()
    if not new_tag:
        raise HTTPException(status_code=400, detail="새 태그 이름을 입력하세요")

    async with db.execute(
        "SELECT id FROM photo_tags WHERE tag = ? AND source = ?", (tag, body.source)
    ) as cur:
        rows = await cur.fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="태그를 찾을 수 없습니다")

    renamed = 0
    for row in rows:
        try:
            await db.execute("UPDATE photo_tags SET tag = ? WHERE id = ?", (new_tag, row["id"]))
            renamed += 1
        except sqlite3.IntegrityError:
            # 같은 사진에 new_tag가 이미 같은 source로 존재 — 중복이므로 옛 행만 지운다
            # (UNIQUE(photo_path, tag, source) 충돌).
            await db.execute("DELETE FROM photo_tags WHERE id = ?", (row["id"],))
    await db.commit()
    return {"tag": new_tag, "source": body.source, "count": renamed}


@router.post("/tags/manual", status_code=201)
async def add_manual_tag(
    body: ManualTagCreate, _: str = Depends(get_current_admin), db=Depends(get_ai_db)
):
    if body.tag not in MANUAL_TAG_VOCAB:
        raise HTTPException(status_code=400, detail="어휘 목록에 없는 태그입니다")
    cur = await db.execute(
        """INSERT INTO photo_tags (photo_path, tag, source) VALUES (?, ?, 'manual')
           ON CONFLICT(photo_path, tag, source) DO NOTHING""",
        (body.photo_path, body.tag),
    )
    await db.commit()
    return {
        "photo_path": body.photo_path, "tag": body.tag, "source": "manual",
        "added": bool(cur.rowcount),
    }
