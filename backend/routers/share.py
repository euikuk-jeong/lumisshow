import asyncio
import os
import time
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse

from backend.models.database import _PHOTO_META_CACHE_VERSION, get_db
from backend.models.schemas import (
    ShareAlbumResponse,
    ShareAuthRequest,
    SharePhotoItem,
    SharePhotosResponse,
    parse_music_paths,
)
from backend.routers.admin_settings import get_settings
from backend.routers.admin_browse import (
    _CACHE_CHUNK,
    _CACHE_INSERT_SQL,
    _meta_to_row,
    _row_to_meta,
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
_FAIL_ENTRY_TTL = _LOCKOUT_SECONDS

# 세션 쿠키(JWT) 기준 조회수 중복 방지: cookie -> expires_at(float)
_counted_sessions: dict[str, float] = {}


async def _purge_stale_failures(db) -> None:
    now = time.time()
    await db.execute(
        """
        DELETE FROM share_link_failures
        WHERE (locked_until > 0 AND ? >= locked_until)
           OR (locked_until = 0 AND ? - recorded_at >= ?)
        """,
        (now, now, _FAIL_ENTRY_TTL),
    )
    await db.commit()


async def _check_lockout(token: str, db) -> None:
    await _purge_stale_failures(db)
    async with db.execute(
        "SELECT fail_count, locked_until FROM share_link_failures WHERE token = ?", (token,)
    ) as cur:
        row = await cur.fetchone()
    if row and row["fail_count"] >= _MAX_ATTEMPTS:
        if time.time() < row["locked_until"]:
            raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")
        await db.execute("DELETE FROM share_link_failures WHERE token = ?", (token,))
        await db.commit()


async def _record_failure(token: str, db) -> None:
    now = time.time()
    async with db.execute(
        "SELECT fail_count FROM share_link_failures WHERE token = ?", (token,)
    ) as cur:
        row = await cur.fetchone()
    count = (row["fail_count"] if row else 0) + 1
    locked_until = now + _LOCKOUT_SECONDS if count >= _MAX_ATTEMPTS else 0.0
    await db.execute(
        "INSERT OR REPLACE INTO share_link_failures (token, fail_count, locked_until, recorded_at) VALUES (?, ?, ?, ?)",
        (token, count, locked_until, now),
    )
    await db.commit()


async def _clear_failures(token: str, db) -> None:
    await db.execute("DELETE FROM share_link_failures WHERE token = ?", (token,))
    await db.commit()


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
    await _check_lockout(token, db)
    link = await _get_valid_link(token, db)
    if link["password_hash"]:
        if not body.password or not verify_password(body.password, link["password_hash"]):
            await _record_failure(token, db)
            raise HTTPException(status_code=401, detail="Invalid password")
    await _clear_failures(token, db)

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
    link = await _get_valid_link(token, db)

    cookie = request.cookies.get(_COOKIE_NAME)
    now = time.time()
    # Evict expired entries to prevent unbounded dict growth in long-running containers
    for k in [k for k, exp in _counted_sessions.items() if exp <= now]:
        del _counted_sessions[k]
    if cookie not in _counted_sessions or _counted_sessions[cookie] <= now:
        _counted_sessions[cookie] = now + _COOKIE_MAX_AGE
        await db.execute(
            "UPDATE albums SET view_count = view_count + 1 WHERE id = ?",
            (link["album_id"],),
        )
        await db.commit()

    async with db.execute(
        """
        SELECT a.name, a.description, a.music_path, a.cover_path, a.created_at,
               a.slideshow_interval, a.slideshow_order, a.slideshow_effect,
               a.slideshow_music, a.slideshow_volume, a.slideshow_loop,
               a.ui_theme, sl.expires_at, COUNT(ap.id) AS photo_count
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

    cover_index = None
    if row["cover_path"]:
        async with db.execute(
            """
            SELECT ap.file_path FROM album_photos ap
            JOIN share_links sl ON sl.album_id = ap.album_id
            WHERE sl.token = ?
            ORDER BY ap.sort_order, ap.id
            """,
            (token,),
        ) as cur2:
            photo_rows = await cur2.fetchall()
        paths = [r["file_path"] for r in photo_rows]
        try:
            cover_index = paths.index(row["cover_path"])
        except ValueError:
            pass

    music_paths = parse_music_paths(row["music_path"])
    sv = await get_settings(db)
    slideshow_defaults = {
        "interval": row["slideshow_interval"] or sv["slideshow_interval"],
        "order":    row["slideshow_order"]    or sv["slideshow_order"],
        "effect":   row["slideshow_effect"]   or sv["slideshow_effect"],
        "music":    bool(row["slideshow_music"]) if row["slideshow_music"] is not None else sv["slideshow_music"],
        "volume":   row["slideshow_volume"]   if row["slideshow_volume"] is not None else sv["slideshow_volume"],
        "loop":     bool(row["slideshow_loop"]) if row["slideshow_loop"] is not None else sv["slideshow_loop"],
    }
    return {
        "album_name": row["name"],
        "description": row["description"],
        "photo_count": row["photo_count"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "has_music": len(music_paths) > 0,
        "music_count": len(music_paths),
        "music_names": [os.path.basename(p) for p in music_paths],
        "cover_index": cover_index,
        "slideshow_defaults": slideshow_defaults,
        "timezone_offset": sv["timezone_offset"],
        "ui_theme": row["ui_theme"] or sv["ui_theme"],
    }


@router.get("/{token}/photos", response_model=SharePhotosResponse)
async def get_photos(
    token: str,
    request: Request,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=0, ge=0),
    db=Depends(get_db),
):
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
        all_rows = await cur.fetchall()

    total = len(all_rows)
    if size > 0:
        offset = (page - 1) * size
        rows = all_rows[offset: offset + size]
    else:
        rows = all_rows

    photo_root = os.path.realpath(os.getenv("PHOTO_ROOT", "./testdata/photos"))

    def _abs(p: str) -> str:
        return p if os.path.isabs(p) else os.path.join(photo_root, p)

    # photo_meta_cache에서 IN 쿼리로 일괄 조회
    rels = [r["file_path"] for r in rows]
    cached: dict[str, dict] = {}
    for i in range(0, len(rels), _CACHE_CHUNK):
        chunk = rels[i:i + _CACHE_CHUNK]
        placeholders = ",".join("?" * len(chunk))
        async with db.execute(
            f"SELECT * FROM photo_meta_cache WHERE cache_version >= ? AND file_path IN ({placeholders})",
            [_PHOTO_META_CACHE_VERSION] + chunk,
        ) as cur:
            for row in await cur.fetchall():
                cached[row["file_path"]] = _row_to_meta(row)

    uncached_rows = [r for r in rows if r["file_path"] not in cached]
    if uncached_rows:
        metas = await asyncio.gather(*[
            asyncio.to_thread(get_image_meta, _abs(r["file_path"])) for r in uncached_rows
        ])
        for r, meta in zip(uncached_rows, metas):
            cached[r["file_path"]] = meta
        # 읽기 성공(width not None)한 경우만 캐시 저장 — 실패 결과는 저장 안 해 다음 요청에 재시도
        inserts = [_meta_to_row(r["file_path"], meta) for r, meta in zip(uncached_rows, metas)
                   if meta.get("width") is not None]
        if inserts:
            await db.executemany(_CACHE_INSERT_SQL, inserts)
        await db.commit()

    photos = []
    for r in rows:
        meta = cached.get(r["file_path"], {})
        photos.append(SharePhotoItem(
            id=r["id"],
            url=f"/media/{quote(r['file_path'])}",
            thumb_small_url=f"/thumb/{quote(r['file_path'])}?size=small",
            thumb_medium_url=f"/thumb/{quote(r['file_path'])}?size=medium",
            filename=os.path.basename(r["file_path"]),
            taken_at=meta.get("taken_at"),
            width=meta.get("width"),
            height=meta.get("height"),
            make=meta.get("make"),
            camera=meta.get("camera"),
            software=meta.get("software"),
            shutter=meta.get("shutter"),
            aperture=meta.get("aperture"),
            iso=meta.get("iso"),
            focal_length=meta.get("focal_length"),
            shoot_mode=meta.get("shoot_mode"),
            flash=meta.get("flash"),
            metering=meta.get("metering"),
            exposure_mode=meta.get("exposure_mode"),
        ))
    return SharePhotosResponse(photos=photos, total=total, page=page)


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

    zip_root = os.path.realpath(os.getenv("PHOTO_ROOT", "./testdata/photos"))
    paths = [
        p if os.path.isabs(p) else os.path.join(zip_root, p)
        for p in (r["file_path"] for r in rows)
    ]
    album_name = rows[0]["album_name"]
    safe_name = "".join(c for c in album_name if c.isalnum() or c in " _-").strip() or "album"
    encoded_name = quote(safe_name + ".zip", safe="")

    return StreamingResponse(
        zip_generator(paths),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )
