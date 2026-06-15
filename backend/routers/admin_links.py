import os
import secrets

from fastapi import APIRouter, Depends, HTTPException

from backend.models.database import get_db
from backend.models.schemas import LinkCreate, LinkResponse, LinkUpdate
from backend.services.auth import get_current_admin, hash_password

router = APIRouter(prefix="/api/admin/albums", tags=["admin-links"])


def _base_url() -> str:
    return os.getenv("BASE_URL", "http://localhost:8080").rstrip("/")


def _row_to_link(row) -> dict:
    d = dict(row)
    d["share_url"] = f"{_base_url()}/s/{d['token']}"
    d["has_password"] = d.pop("password_hash") is not None
    return d


async def _get_album_or_404(album_id: int, db):
    async with db.execute("SELECT id FROM albums WHERE id = ?", (album_id,)) as cur:
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Album not found")


async def _get_link_or_404(album_id: int, link_id: int, db) -> dict:
    async with db.execute(
        "SELECT * FROM share_links WHERE id = ? AND album_id = ?",
        (link_id, album_id),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Link not found")
    return row


# ── 엔드포인트 ────────────────────────────────────────────────────────────────

@router.get("/{album_id}/links", response_model=list[LinkResponse])
async def list_links(
    album_id: int,
    _: str = Depends(get_current_admin),
    db=Depends(get_db),
):
    await _get_album_or_404(album_id, db)
    async with db.execute(
        "SELECT * FROM share_links WHERE album_id = ? ORDER BY created_at DESC",
        (album_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [_row_to_link(r) for r in rows]


@router.post("/{album_id}/links", response_model=LinkResponse, status_code=201)
async def create_link(
    album_id: int,
    body: LinkCreate,
    _: str = Depends(get_current_admin),
    db=Depends(get_db),
):
    await _get_album_or_404(album_id, db)
    token = secrets.token_hex(5)
    password_hash = hash_password(body.password) if body.password else None
    async with db.execute(
        "INSERT INTO share_links (album_id, token, password_hash, expires_at) VALUES (?, ?, ?, ?)",
        (album_id, token, password_hash, body.expires_at),
    ) as cur:
        link_id = cur.lastrowid
    await db.commit()

    async with db.execute(
        "SELECT * FROM share_links WHERE id = ?", (link_id,)
    ) as cur:
        row = await cur.fetchone()
    return _row_to_link(row)


@router.patch("/{album_id}/links/{link_id}", response_model=LinkResponse)
async def update_link(
    album_id: int,
    link_id: int,
    body: LinkUpdate,
    _: str = Depends(get_current_admin),
    db=Depends(get_db),
):
    await _get_link_or_404(album_id, link_id, db)
    updates = body.model_dump(exclude_unset=True)

    if "password" in updates:
        raw = updates.pop("password")
        updates["password_hash"] = hash_password(raw) if raw else None

    if updates:
        cols = ", ".join(f"{k} = ?" for k in updates)
        await db.execute(
            f"UPDATE share_links SET {cols} WHERE id = ? AND album_id = ?",
            (*updates.values(), link_id, album_id),
        )
        await db.commit()

    async with db.execute(
        "SELECT * FROM share_links WHERE id = ?", (link_id,)
    ) as cur:
        row = await cur.fetchone()
    return _row_to_link(row)


@router.delete("/{album_id}/links/{link_id}", status_code=204)
async def delete_link(
    album_id: int,
    link_id: int,
    _: str = Depends(get_current_admin),
    db=Depends(get_db),
):
    await _get_link_or_404(album_id, link_id, db)
    await db.execute(
        "DELETE FROM share_links WHERE id = ? AND album_id = ?", (link_id, album_id)
    )
    await db.commit()
