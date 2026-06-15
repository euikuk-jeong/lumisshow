import asyncio
import os
import time
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from backend.models.database import get_db
from backend.models.schemas import (
    ShareAlbumResponse,
    ShareAuthRequest,
    SharePhotoItem,
    SharePhotosResponse,
    parse_music_paths,
)
from backend.services.auth import (
    create_share_session_token,
    verify_password,
    verify_share_session_cookie,
)
from backend.services.thumbnail import get_image_meta
from backend.services.zip_stream import zip_generator

router = APIRouter(prefix="/api/share", tags=["share"])

_COOKIE_NAME = "share_session"
_COOKIE_MAX_AGE = 24 * 3600

_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 15 * 60
# token -> (fail_count, locked_until: float)
_fail_registry: dict[str, tuple[int, float]] = {}


def _check_lockout(token: str) -> None:
    entry = _fail_registry.get(token)
    if entry is None:
        return
    count, locked_until = entry
    if count >= _MAX_ATTEMPTS:
        if time.time() < locked_until:
            raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")
        del _fail_registry[token]


def _record_failure(token: str) -> None:
    count, _ = _fail_registry.get(token, (0, 0.0))
    count += 1
    locked_until = time.time() + _LOCKOUT_SECONDS if count >= _MAX_ATTEMPTS else 0.0
    _fail_registry[token] = (count, locked_until)


def _clear_failures(token: str) -> None:
    _fail_registry.pop(token, None)


async def _get_valid_link(token: str, db):
    """토큰 존재, 활성, 미만료 검사. 실패 시 404."""
    async with db.execute(
        "SELECT * FROM share_links WHERE token = ? AND is_active = 1",
        (token,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Link not found")

    if row["expires_at"]:
        expires = datetime.fromisoformat(str(row["expires_at"]))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            raise HTTPException(status_code=404, detail="Link expired")

    return row


# ── 공개 엔드포인트 ────────────────────────────────────────────────────────────

@router.get("/{token}")
async def get_link_info(token: str, db=Depends(get_db)):
    """패스워드 필요 여부 반환. 프론트엔드가 비밀번호 입력 폼 표시 여부 결정에 사용."""
    link = await _get_valid_link(token, db)
    return {"requires_password": link["password_hash"] is not None}


@router.post("/{token}/auth")
async def auth_link(
    token: str,
    body: ShareAuthRequest,
    response: Response,
    db=Depends(get_db),
):
    """패스워드 검증 후 httpOnly 세션 쿠키 발급."""
    _check_lockout(token)
    link = await _get_valid_link(token, db)
    if link["password_hash"]:
        if not body.password or not verify_password(body.password, link["password_hash"]):
            _record_failure(token)
            raise HTTPException(status_code=401, detail="Invalid password")
    _clear_failures(token)

    session_jwt = create_share_session_token(token)
    base_url = os.getenv("BASE_URL", "")
    response.set_cookie(
        key=_COOKIE_NAME,
        value=session_jwt,
        httponly=True,
        max_age=_COOKIE_MAX_AGE,
        samesite="lax",
        secure=base_url.startswith("https://"),
    )
    return {"ok": True}


# ── 인증 필요 엔드포인트 ──────────────────────────────────────────────────────

@router.get("/{token}/album", response_model=ShareAlbumResponse)
async def get_album(token: str, request: Request, db=Depends(get_db)):
    verify_share_session_cookie(token, request.cookies.get(_COOKIE_NAME))
    await _get_valid_link(token, db)

    async with db.execute(
        """
        SELECT a.name, a.description, a.music_path, a.created_at,
               sl.expires_at, COUNT(ap.id) AS photo_count
        FROM share_links sl
        JOIN albums a ON a.id = sl.album_id
        LEFT JOIN album_photos ap ON ap.album_id = a.id
        WHERE sl.token = ? AND sl.is_active = 1
        GROUP BY a.id
        """,
        (token,),
    ) as cur:
        row = await cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Album not found")

    music_paths = parse_music_paths(row["music_path"])
    return {
        "album_name": row["name"],
        "description": row["description"],
        "photo_count": row["photo_count"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "has_music": len(music_paths) > 0,
        "music_count": len(music_paths),
        "music_names": [os.path.basename(p) for p in music_paths],
    }


@router.get("/{token}/photos", response_model=SharePhotosResponse)
async def get_photos(token: str, request: Request, db=Depends(get_db)):
    verify_share_session_cookie(token, request.cookies.get(_COOKIE_NAME))
    await _get_valid_link(token, db)

    async with db.execute(
        """
        SELECT ap.id, ap.file_path
        FROM share_links sl
        JOIN album_photos ap ON ap.album_id = sl.album_id
        WHERE sl.token = ? AND sl.is_active = 1
        ORDER BY ap.sort_order, ap.id
        """,
        (token,),
    ) as cur:
        rows = await cur.fetchall()

    metas = await asyncio.gather(*[
        asyncio.to_thread(get_image_meta, r["file_path"]) for r in rows
    ])

    photos = [
        SharePhotoItem(
            id=r["id"],
            url=f"/media/{quote(r['file_path'])}",
            thumb_small_url=f"/thumb/{quote(r['file_path'])}?size=small",
            thumb_medium_url=f"/thumb/{quote(r['file_path'])}?size=medium",
            filename=os.path.basename(r["file_path"]),
            taken_at=meta["taken_at"],
            width=meta["width"],
            height=meta["height"],
            make=meta["make"],
            camera=meta["camera"],
            software=meta["software"],
            shutter=meta["shutter"],
            aperture=meta["aperture"],
            iso=meta["iso"],
            focal_length=meta["focal_length"],
            shoot_mode=meta["shoot_mode"],
            flash=meta["flash"],
            metering=meta["metering"],
            exposure_mode=meta["exposure_mode"],
        )
        for r, meta in zip(rows, metas)
    ]
    return SharePhotosResponse(photos=photos, total=len(photos))


@router.get("/{token}/download")
async def download_zip(token: str, request: Request, db=Depends(get_db)):
    """앨범 전체 ZIP 다운로드 (스트리밍)."""
    verify_share_session_cookie(token, request.cookies.get(_COOKIE_NAME))
    await _get_valid_link(token, db)

    async with db.execute(
        """
        SELECT ap.file_path, a.name AS album_name
        FROM share_links sl
        JOIN albums a ON a.id = sl.album_id
        JOIN album_photos ap ON ap.album_id = sl.album_id
        WHERE sl.token = ? AND sl.is_active = 1
          AND (sl.expires_at IS NULL OR sl.expires_at > datetime('now'))
        ORDER BY ap.sort_order, ap.id
        """,
        (token,),
    ) as cur:
        rows = await cur.fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="No photos in album")

    paths = [r["file_path"] for r in rows]
    album_name = rows[0]["album_name"]
    safe_name = "".join(c for c in album_name if c.isalnum() or c in " _-").strip() or "album"
    encoded_name = quote(safe_name + ".zip", safe="")

    return StreamingResponse(
        zip_generator(paths),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )
