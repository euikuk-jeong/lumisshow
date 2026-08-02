"""Admin 태그 관리 API — ai.db photo_tags 기반 (Phase 5, doc/tagging_requirement.md
"Admin 태그 관리 화면" 절).

source='person'은 다루지 않는다 — admin_people.py가 face_labels 변경 시마다
_sync_person_tag()로 이미 전담 관리 중이라, 이 화면에서 photo_tags(source='person')를
직접 건드리면 두 화면이 서로 다른 경로로 같은 행을 써서 동기화가 깨질 위험이 있다.

source='location'은 조회만 지원한다(목록·사진 그리드는 노출하되 rename/delete는 막음) —
photo_locations가 정본이고 photo_tags는 검색용 복제본이라, 여기서 태그만 지우면
photo_locations와 어긋난다. 수동 교정은 photo_locations 전용 UI가 필요(이번 범위 아님,
doc의 "추후 UI" 항목).

/tags/xmp-export(Phase 7)는 위 태그 CRUD와 무관한 별도 기능(DB → XMP 사이드카
일괄 내보내기)이지만, doc 설계상 같은 라우터에 배치하기로 확정돼 있어 여기 둔다.
"""

import os
import sqlite3
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.models.ai_database import get_ai_db
from backend.models.database import get_db
from backend.models.schemas import (
    ManualTagCreate,
    SharePhotosResponse,
    TagRenameRequest,
    build_share_photo_item,
)
from backend.services.auth import admin_image_auth, get_current_admin
from backend.services.photo_meta import load_photo_meta
from backend.services.photo_tags import load_photo_tags
from backend.services.tag_vocab import MANUAL_TAG_VOCAB
from backend.services.xmp_export import (
    XMP_EXPORT_TAG_SOURCES,
    has_exportable_content,
    load_confirmed_regions,
    load_locations,
    xmp_bytes_iter,
)
from backend.services.zip_stream import zip_generator_from_content

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


@router.get("/tags/xmp-export")
async def export_xmp(
    _: str = Depends(admin_image_auth), db=Depends(get_ai_db), app_db=Depends(get_db)
):
    """DB 메타데이터(태그·위치·확정 인물)를 사진별 .xmp 사이드카로 묶어 ZIP 스트리밍
    다운로드한다(Phase 7, doc/tagging_requirement.md "XMP export 상세 설계" 절).
    원본과 동일한 상대 폴더 구조를 유지 — 원본 파일은 절대 수정하지 않는다.

    admin_image_auth(Bearer 또는 admin_img_session 쿠키)를 쓰는 이유: 관리자 UI에서
    JS blob 다운로드 없이 단순 <a href download> 링크로 트리거하기 위함 — /thumb,
    /photo, /faces/{id}/crop과 동일한 패턴."""
    async with db.execute(
        """SELECT DISTINCT photo_path FROM (
             SELECT photo_path FROM photo_tags
             UNION
             SELECT photo_path FROM photo_locations
             UNION
             SELECT f.photo_path FROM faces f
               JOIN face_labels fl ON fl.face_id = f.id
              WHERE fl.person_id IS NOT NULL
           ) ORDER BY photo_path"""
    ) as cur:
        paths = [r["photo_path"] for r in await cur.fetchall()]

    tags_map = await load_photo_tags(paths, db, XMP_EXPORT_TAG_SOURCES)
    locations_map = await load_locations(paths, db)
    regions_map = await load_confirmed_regions(paths, db)
    # width/height는 mwg-rs:Regions 정규화에만 쓰인다 — 확정 얼굴이 있는 사진만
    # 조회해 라이브러리 전체 규모의 EXIF 재확인(NAS I/O 폭주)을 피한다.
    meta_map = await load_photo_meta(list(regions_map.keys()), app_db)

    # items의 각 content는 완성된 문자열이 아니라 xmp_bytes_iter()가 반환하는
    # 제너레이터 — zipstream이 실제 인코딩할 때(스트리밍 중, 한 항목씩)까지 본문
    # 생성을 미뤄서 45,000장 규모에서도 전체를 한꺼번에 메모리에 올리지 않는다.
    items: list[tuple[str, object]] = []
    seen_arcnames: set[str] = set()
    for p in paths:
        # tags_map[p]는 source별로 나뉜 dict — dc:subject는 소스 구분 없이 전체를
        # 합친다(XMP export는 정보 패널과 달리 프라이버시 구분이 없는 개인 백업용).
        # 여러 source에 같은 텍스트가 있을 수 있어(예: 위치 "서울" + 폴더명 "서울")
        # 순서를 유지한 채 중복을 제거한다.
        seen: set[str] = set()
        tags: list[str] = []
        for source in XMP_EXPORT_TAG_SOURCES:
            for t in tags_map.get(p, {}).get(source, []):
                if t not in seen:
                    seen.add(t)
                    tags.append(t)

        regions = regions_map.get(p, [])
        location = locations_map.get(p)
        meta = meta_map.get(p, {})
        width, height = meta.get("width"), meta.get("height")
        if not has_exportable_content(tags, regions, location, width, height):
            continue
        # 확장자만 .xmp로 바꾼 stem은 photo_path와 달리 유일하지 않다(RAW+JPEG처럼
        # 같은 폴더에 스템이 같은 파일 쌍이 있으면 충돌) — 충돌 시 원본 파일명 전체에
        # .xmp를 붙여 photo_path 유일성을 그대로 물려받는 이름으로 대체.
        arcname = os.path.splitext(p)[0] + ".xmp"
        if arcname in seen_arcnames:
            arcname = p + ".xmp"
        seen_arcnames.add(arcname)
        items.append((arcname, xmp_bytes_iter(tags, regions, location, width, height)))

    filename = f"lumisshow-xmp-export-{datetime.now():%Y%m%d}.zip"
    return StreamingResponse(
        zip_generator_from_content(items),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )
