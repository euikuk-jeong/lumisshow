import asyncio
import json
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from backend.models.database import get_db
from backend.models.schemas import (
    AlbumCreate,
    AlbumDetail,
    AlbumResponse,
    AlbumUpdate,
    PhotoOrderRequest,
    PhotoPathsRequest,
    parse_music_paths,
)
from backend.routers.admin_settings import get_settings
from backend.services.auth import get_current_admin
from backend.services.thumbnail import get_image_meta

router = APIRouter(prefix="/api/admin/albums", tags=["admin-albums"])


def _resolve_paths(paths: list[str]) -> list[str]:
    """경로를 PHOTO_ROOT 기준 상대 경로로 정규화. 절대 경로도 상대로 변환."""
    root = os.path.realpath(os.getenv("PHOTO_ROOT", "./testdata/photos"))
    result = []
    for p in paths:
        abs_path = os.path.realpath(p if os.path.isabs(p) else os.path.join(root, p))
        try:
            result.append(os.path.relpath(abs_path, root).replace("\\", "/"))
        except ValueError:
            result.append(p)  # Windows 다른 드라이브 간 경로: 원본 유지
    return result

_SLIDESHOW_DEFAULTS = {
    "slideshow_interval": 5,
    "slideshow_order": "sequential",
    "slideshow_effect": "random",
    "slideshow_music": True,
    "slideshow_volume": 25,
    "slideshow_loop": True,
}

_PHOTO_SORT_DEFAULTS = {
    "photo_sort_by": "taken_at",
    "photo_sort_dir": "asc",
}

_ALLOWED_UPDATE_COLS = {
    "name", "description", "cover_path",
    "slideshow_interval", "slideshow_order", "slideshow_effect",
    "slideshow_music", "slideshow_volume", "slideshow_loop",
    "photo_sort_by", "photo_sort_dir", "ui_theme",
}


async def _get_album_or_404(album_id: int, db):
    async with db.execute("SELECT id FROM albums WHERE id = ?", (album_id,)) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Album not found")


def _row_to_album_dict(row) -> dict:
    d = dict(row)
    d['music_paths'] = parse_music_paths(d.pop('music_path', None))
    # NULL(기존 앨범) → 기본값으로 채움
    for col, default in _SLIDESHOW_DEFAULTS.items():
        if d.get(col) is None:
            d[col] = default
    for col, default in _PHOTO_SORT_DEFAULTS.items():
        if d.get(col) is None:
            d[col] = default
    for col in ('slideshow_music', 'slideshow_loop'):
        if not isinstance(d[col], bool):
            d[col] = bool(d[col])
    return d


async def _apply_photo_sort(album_id: int, sort_by: str, sort_dir: str, db) -> None:
    """앨범 사진들의 sort_order를 지정 기준으로 재설정."""
    async with db.execute(
        "SELECT id, file_path FROM album_photos WHERE album_id = ? ORDER BY id",
        (album_id,),
    ) as cur:
        rows = await cur.fetchall()
    if not rows:
        return

    reverse = sort_dir == "desc"

    if sort_by == "taken_at":
        root = os.path.realpath(os.getenv("PHOTO_ROOT", "./testdata/photos"))

        def _abs(p: str) -> str:
            return p if os.path.isabs(p) else os.path.join(root, p)

        metas = await asyncio.gather(*[
            asyncio.to_thread(get_image_meta, _abs(r["file_path"])) for r in rows
        ])
        # taken_at None → datetime.min, 동일 날짜면 파일명으로 tiebreak
        combined = sorted(
            zip(rows, metas),
            key=lambda pair: (
                pair[1]["taken_at"] or datetime.min,
                os.path.basename(pair[0]["file_path"]).lower(),
            ),
            reverse=reverse,
        )
        sorted_ids = [r["id"] for r, _ in combined]
    else:  # filename (default)
        sorted_rows = sorted(
            rows,
            key=lambda r: os.path.basename(r["file_path"]).lower(),
            reverse=reverse,
        )
        sorted_ids = [r["id"] for r in sorted_rows]

    await db.executemany(
        "UPDATE album_photos SET sort_order = ? WHERE id = ?",
        [(i, pid) for i, pid in enumerate(sorted_ids)],
    )


async def _fetch_album(album_id: int, db) -> dict:
    async with db.execute(
        """
        SELECT a.*, COUNT(p.id) AS photo_count,
          (SELECT file_path FROM album_photos WHERE album_id = a.id ORDER BY sort_order, id LIMIT 1) AS first_photo_path
        FROM albums a LEFT JOIN album_photos p ON p.album_id = a.id
        WHERE a.id = ?
        GROUP BY a.id
        """,
        (album_id,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Album not found")
    return _row_to_album_dict(row)


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[AlbumResponse])
async def list_albums(_: str = Depends(get_current_admin), db=Depends(get_db)):
    async with db.execute(
        """
        SELECT a.*, COUNT(p.id) AS photo_count,
          (SELECT file_path FROM album_photos WHERE album_id = a.id ORDER BY sort_order, id LIMIT 1) AS first_photo_path
        FROM albums a LEFT JOIN album_photos p ON p.album_id = a.id
        GROUP BY a.id ORDER BY a.created_at DESC
        """
    ) as cur:
        rows = await cur.fetchall()
    return [_row_to_album_dict(r) for r in rows]


@router.post("", response_model=AlbumResponse, status_code=201)
async def create_album(
    body: AlbumCreate,
    _: str = Depends(get_current_admin),
    db=Depends(get_db),
):
    sv = await get_settings(db)
    async with db.execute(
        """INSERT INTO albums
           (name, description,
            slideshow_interval, slideshow_order, slideshow_effect,
            slideshow_music, slideshow_volume, slideshow_loop,
            photo_sort_by, photo_sort_dir, ui_theme)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (body.name, body.description,
         sv["slideshow_interval"], sv["slideshow_order"], sv["slideshow_effect"],
         int(sv["slideshow_music"]), sv["slideshow_volume"], int(sv["slideshow_loop"]),
         _PHOTO_SORT_DEFAULTS["photo_sort_by"], _PHOTO_SORT_DEFAULTS["photo_sort_dir"],
         sv.get("ui_theme", "dark")),
    ) as cur:
        album_id = cur.lastrowid

    if body.photo_paths:
        resolved = _resolve_paths(body.photo_paths)
        await db.executemany(
            "INSERT OR IGNORE INTO album_photos (album_id, file_path, sort_order) VALUES (?, ?, ?)",
            [(album_id, path, i) for i, path in enumerate(resolved)],
        )
        await _apply_photo_sort(album_id, _PHOTO_SORT_DEFAULTS["photo_sort_by"], _PHOTO_SORT_DEFAULTS["photo_sort_dir"], db)

    await db.commit()
    return await _fetch_album(album_id, db)


@router.get("/{album_id}", response_model=AlbumDetail)
async def get_album(
    album_id: int,
    _: str = Depends(get_current_admin),
    db=Depends(get_db),
):
    album = await _fetch_album(album_id, db)

    async with db.execute(
        "SELECT * FROM album_photos WHERE album_id = ? ORDER BY sort_order, id",
        (album_id,),
    ) as cur:
        photo_rows = await cur.fetchall()

    album["photos"] = [dict(r) for r in photo_rows]
    return album


@router.put("/{album_id}", response_model=AlbumResponse)
async def update_album(
    album_id: int,
    body: AlbumUpdate,
    _: str = Depends(get_current_admin),
    db=Depends(get_db),
):
    body_data = body.model_dump(exclude_unset=True)
    # photo_sort_by / photo_sort_dir 유효성 검사
    if body_data.get('photo_sort_by') not in (None, 'filename', 'taken_at'):
        body_data['photo_sort_by'] = 'filename'
    if body_data.get('photo_sort_dir') not in (None, 'asc', 'desc'):
        body_data['photo_sort_dir'] = 'asc'
    updates = {k: v for k, v in body_data.items() if k in _ALLOWED_UPDATE_COLS}
    if 'music_paths' in body_data:
        updates['music_path'] = (
            json.dumps(body_data['music_paths']) if body_data['music_paths'] else None
        )
    # SQLite는 bool을 INTEGER로 저장
    for col in ('slideshow_music', 'slideshow_loop'):
        if col in updates and isinstance(updates[col], bool):
            updates[col] = int(updates[col])
    if updates:
        cols = ", ".join(f"{k} = ?" for k in updates)
        await db.execute(
            f"UPDATE albums SET {cols}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (*updates.values(), album_id),
        )
        # photo_sort 설정이 변경된 경우 sort_order 재설정
        if 'photo_sort_by' in updates or 'photo_sort_dir' in updates:
            async with db.execute(
                "SELECT photo_sort_by, photo_sort_dir FROM albums WHERE id = ?", (album_id,)
            ) as cur:
                row = await cur.fetchone()
            await _apply_photo_sort(
                album_id,
                row["photo_sort_by"] or _PHOTO_SORT_DEFAULTS["photo_sort_by"],
                row["photo_sort_dir"] or _PHOTO_SORT_DEFAULTS["photo_sort_dir"],
                db,
            )
        await db.commit()
    return await _fetch_album(album_id, db)


@router.delete("/{album_id}/view-count", status_code=204)
async def reset_view_count(
    album_id: int,
    _: str = Depends(get_current_admin),
    db=Depends(get_db),
):
    await _get_album_or_404(album_id, db)
    await db.execute("UPDATE albums SET view_count = 0 WHERE id = ?", (album_id,))
    await db.commit()


@router.delete("/{album_id}", status_code=204)
async def delete_album(
    album_id: int,
    _: str = Depends(get_current_admin),
    db=Depends(get_db),
):
    await _get_album_or_404(album_id, db)
    await db.execute("DELETE FROM albums WHERE id = ?", (album_id,))
    await db.commit()


# ── 사진 관리 ─────────────────────────────────────────────────────────────────

@router.post("/{album_id}/photos", status_code=204)
async def add_photos(
    album_id: int,
    body: PhotoPathsRequest,
    _: str = Depends(get_current_admin),
    db=Depends(get_db),
):
    await _get_album_or_404(album_id, db)
    await db.executemany(
        """
        INSERT OR IGNORE INTO album_photos (album_id, file_path, sort_order)
        VALUES (?, ?, (SELECT COALESCE(MAX(sort_order), -1) + 1 FROM album_photos WHERE album_id = ?))
        """,
        [(album_id, path, album_id) for path in _resolve_paths(body.photo_paths)],
    )
    # 사진 추가 후 앨범 sort 설정에 맞게 재정렬
    async with db.execute(
        "SELECT photo_sort_by, photo_sort_dir FROM albums WHERE id = ?", (album_id,)
    ) as cur:
        row = await cur.fetchone()
    await _apply_photo_sort(
        album_id,
        row["photo_sort_by"] or _PHOTO_SORT_DEFAULTS["photo_sort_by"],
        row["photo_sort_dir"] or _PHOTO_SORT_DEFAULTS["photo_sort_dir"],
        db,
    )
    await db.commit()


@router.delete("/{album_id}/photos", status_code=204)
async def remove_photos(
    album_id: int,
    body: PhotoPathsRequest,
    _: str = Depends(get_current_admin),
    db=Depends(get_db),
):
    await _get_album_or_404(album_id, db)
    await db.executemany(
        "DELETE FROM album_photos WHERE album_id = ? AND file_path = ?",
        [(album_id, path) for path in _resolve_paths(body.photo_paths)],
    )
    await db.commit()


@router.put("/{album_id}/photos/order", status_code=204)
async def reorder_photos(
    album_id: int,
    body: PhotoOrderRequest,
    _: str = Depends(get_current_admin),
    db=Depends(get_db),
):
    await _get_album_or_404(album_id, db)
    await db.executemany(
        "UPDATE album_photos SET sort_order = ? WHERE id = ? AND album_id = ?",
        [(item.sort_order, item.id, album_id) for item in body.orders],
    )
    await db.commit()
