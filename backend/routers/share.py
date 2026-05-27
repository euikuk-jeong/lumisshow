from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from backend.models.database import get_db
from backend.models.schemas import (
    ShareAlbumResponse,
    ShareAuthRequest,
    SharePhotoItem,
    SharePhotosResponse,
)
from backend.services.auth import (
    create_share_session_token,
    verify_password,
    verify_share_session_cookie,
)

router = APIRouter(prefix="/api/share", tags=["share"])

_COOKIE_NAME = "share_session"
_COOKIE_MAX_AGE = 24 * 3600


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
    link = await _get_valid_link(token, db)
    if link["password_hash"]:
        if not body.password or not verify_password(body.password, link["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid password")

    session_jwt = create_share_session_token(token)
    response.set_cookie(
        key=_COOKIE_NAME,
        value=session_jwt,
        httponly=True,
        max_age=_COOKIE_MAX_AGE,
        samesite="lax",
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
        WHERE sl.token = ?
        GROUP BY a.id
        """,
        (token,),
    ) as cur:
        row = await cur.fetchone()

    return {
        "album_name": row["name"],
        "description": row["description"],
        "photo_count": row["photo_count"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "has_music": row["music_path"] is not None,
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
        WHERE sl.token = ?
        ORDER BY ap.sort_order, ap.id
        """,
        (token,),
    ) as cur:
        rows = await cur.fetchall()

    photos = [
        SharePhotoItem(
            id=r["id"],
            url=f"/media/{quote(r['file_path'])}",
            thumb_small_url=f"/thumb/{quote(r['file_path'])}?size=small",
            thumb_medium_url=f"/thumb/{quote(r['file_path'])}?size=medium",
            width=None,
            height=None,
        )
        for r in rows
    ]
    return SharePhotosResponse(photos=photos, total=len(photos))
