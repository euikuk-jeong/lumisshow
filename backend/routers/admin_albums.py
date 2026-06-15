import json
import os

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
from backend.services.auth import get_current_admin

router = APIRouter(prefix="/api/admin/albums", tags=["admin-albums"])


def _resolve_paths(paths: list[str]) -> list[str]:
    """상대 경로를 PHOTO_ROOT 기준 절대 경로로 변환. 절대 경로는 그대로 통과."""
    root = os.path.realpath(os.getenv("PHOTO_ROOT", "./testdata/photos"))
    return [
        os.path.realpath(os.path.join(root, p)) if not os.path.isabs(p) else os.path.realpath(p)
        for p in paths
    ]

_ALLOWED_UPDATE_COLS = {"name", "description", "cover_path"}


async def _get_album_or_404(album_id: int, db):
    async with db.execute("SELECT id FROM albums WHERE id = ?", (album_id,)) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Album not found")


def _row_to_album_dict(row) -> dict:
    d = dict(row)
    d['music_paths'] = parse_music_paths(d.pop('music_path', None))
    return d


async def _fetch_album(album_id: int, db) -> dict:
    async with db.execute(
        """
        SELECT a.*, COUNT(p.id) AS photo_count
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
        SELECT a.*, COUNT(p.id) AS photo_count
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
    async with db.execute(
        "INSERT INTO albums (name, description) VALUES (?, ?)",
        (body.name, body.description),
    ) as cur:
        album_id = cur.lastrowid

    if body.photo_paths:
        await db.executemany(
            "INSERT OR IGNORE INTO album_photos (album_id, file_path, sort_order) VALUES (?, ?, ?)",
            [(album_id, path, i) for i, path in enumerate(_resolve_paths(body.photo_paths))],
        )

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
    updates = {k: v for k, v in body_data.items() if k in _ALLOWED_UPDATE_COLS}
    if 'music_paths' in body_data:
        updates['music_path'] = (
            json.dumps(body_data['music_paths']) if body_data['music_paths'] else None
        )
    if updates:
        cols = ", ".join(f"{k} = ?" for k in updates)
        await db.execute(
            f"UPDATE albums SET {cols}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (*updates.values(), album_id),
        )
        await db.commit()
    return await _fetch_album(album_id, db)


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
