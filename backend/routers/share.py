import asyncio
import os
import time
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, StreamingResponse

from backend.models.database import get_db
from backend.models.schemas import (
    ShareAlbumResponse,
    ShareAuthRequest,
    SharePhotosResponse,
    build_share_photo_item,
    parse_music_paths,
)
from backend.routers.admin_settings import get_settings
from backend.routers.admin_browse import load_photo_meta
from backend.routers.media import _assert_within_photo_root, _resolve_abs
from backend.services.auth import (
    create_share_session_token,
    verify_password,
    verify_share_session_cookie,
)
from backend.services.thumbnail import generate_thumbnail
from backend.services.zip_stream import zip_generator

router = APIRouter(prefix="/api/share", tags=["share"])

_COOKIE_NAME = "share_session"
_COOKIE_MAX_AGE = 24 * 3600

_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 15 * 60
_FAIL_ENTRY_TTL = _LOCKOUT_SECONDS

# 공개 GET 엔드포인트(토큰 존재 여부 노출) 속도 제한 — IP당 창구간 최대 요청 수
_RATE_LIMIT_WINDOW = 60
_RATE_LIMIT_MAX = 30

# 세션 쿠키(JWT) 기준 조회수 중복 방지: cookie -> expires_at(float)
_counted_sessions: dict[str, float] = {}


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _lockout_key(token: str, request: Request) -> str:
    """브루트포스 잠금 키를 IP+token 복합으로 구성 — token 단독 키는 공격자가
    일부러 5회 오입력해 정상 사용자까지 15분 차단시킬 수 있어 IP를 함께 묶는다."""
    return f"{_client_ip(request)}:{token}"


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


async def _check_lockout(key: str, db) -> None:
    await _purge_stale_failures(db)
    async with db.execute(
        "SELECT fail_count, locked_until FROM share_link_failures WHERE token = ?", (key,)
    ) as cur:
        row = await cur.fetchone()
    if row and row["fail_count"] >= _MAX_ATTEMPTS:
        if time.time() < row["locked_until"]:
            raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")
        await db.execute("DELETE FROM share_link_failures WHERE token = ?", (key,))
        await db.commit()


async def _record_failure(key: str, db) -> None:
    now = time.time()
    async with db.execute(
        "SELECT fail_count FROM share_link_failures WHERE token = ?", (key,)
    ) as cur:
        row = await cur.fetchone()
    count = (row["fail_count"] if row else 0) + 1
    locked_until = now + _LOCKOUT_SECONDS if count >= _MAX_ATTEMPTS else 0.0
    await db.execute(
        "INSERT OR REPLACE INTO share_link_failures (token, fail_count, locked_until, recorded_at) VALUES (?, ?, ?, ?)",
        (key, count, locked_until, now),
    )
    await db.commit()


async def _clear_failures(key: str, db) -> None:
    await db.execute("DELETE FROM share_link_failures WHERE token = ?", (key,))
    await db.commit()


async def _purge_stale_rate_limits(db) -> None:
    now = time.time()
    await db.execute(
        "DELETE FROM public_rate_limit WHERE ? - window_start >= ?",
        (now, _RATE_LIMIT_WINDOW),
    )
    await db.commit()


async def _check_public_rate_limit(request: Request, db) -> None:
    """존재하지 않는 토큰(404) 조회만 카운트 — 정상 사용자의 200 응답은 절대
    잠금에 영향을 주지 않는다 (IP당 60초에 30회 404 시 429).
    가입 로그인 잠금(_check_lockout)과 동일하게 실패만 세는 방식."""
    await _purge_stale_rate_limits(db)
    ip = _client_ip(request)
    now = time.time()
    async with db.execute(
        "SELECT count, window_start FROM public_rate_limit WHERE key = ?", (ip,)
    ) as cur:
        row = await cur.fetchone()
    if row and now - row["window_start"] < _RATE_LIMIT_WINDOW and row["count"] >= _RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Too many requests")


async def _record_invalid_token_probe(request: Request, db) -> None:
    ip = _client_ip(request)
    now = time.time()
    async with db.execute(
        "SELECT count, window_start FROM public_rate_limit WHERE key = ?", (ip,)
    ) as cur:
        row = await cur.fetchone()
    if row is None or now - row["window_start"] >= _RATE_LIMIT_WINDOW:
        count, window_start = 1, now
    else:
        count, window_start = row["count"] + 1, row["window_start"]
    await db.execute(
        "INSERT OR REPLACE INTO public_rate_limit (key, count, window_start) VALUES (?, ?, ?)",
        (ip, count, window_start),
    )
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


async def _get_valid_link_tracked(token: str, request: Request, db):
    """_get_valid_link + 존재하지 않는/만료된 토큰(404) 조회 시 enumeration
    카운터 증가. 공개 GET 엔드포인트 전용 — 정상 토큰 조회는 카운트하지 않는다."""
    try:
        return await _get_valid_link(token, db)
    except HTTPException as e:
        if e.status_code == 404:
            await _record_invalid_token_probe(request, db)
        raise


# ── 공개 엔드포인트 ────────────────────────────────────────────────────────────

@router.get("/{token}")
async def get_link_info(token: str, request: Request, db=Depends(get_db)):
    """패스워드 필요 여부 반환. 프론트엔드가 비밀번호 입력 폼 표시 여부 결정에 사용."""
    await _check_public_rate_limit(request, db)
    link = await _get_valid_link_tracked(token, request, db)
    return {"requires_password": link["password_hash"] is not None}


@router.post("/{token}/auth")
async def auth_link(
    token: str,
    body: ShareAuthRequest,
    request: Request,
    response: Response,
    db=Depends(get_db),
):
    """패스워드 검증 후 httpOnly 세션 쿠키 발급."""
    key = _lockout_key(token, request)
    await _check_lockout(key, db)
    link = await _get_valid_link(token, db)
    if link["password_hash"]:
        if not body.password or not await asyncio.to_thread(verify_password, body.password, link["password_hash"]):
            await _record_failure(key, db)
            raise HTTPException(status_code=401, detail="Invalid password")
    await _clear_failures(key, db)

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
        SELECT COUNT(*) AS n
        FROM share_links sl
        JOIN album_photos ap ON ap.album_id = sl.album_id
        WHERE sl.token = ? AND sl.is_active = 1
        """,
        (token,),
    ) as cur:
        total = (await cur.fetchone())["n"]

    query = """
        SELECT ap.id, ap.file_path
        FROM share_links sl
        JOIN album_photos ap ON ap.album_id = sl.album_id
        WHERE sl.token = ? AND sl.is_active = 1
        ORDER BY ap.sort_order, ap.id
    """
    params: list = [token]
    if size > 0:
        query += " LIMIT ? OFFSET ?"
        params += [size, (page - 1) * size]

    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()

    # photo_meta_cache에서 IN 쿼리로 일괄 조회 (미스는 EXIF 읽어 캐시)
    cached = await load_photo_meta([r["file_path"] for r in rows], db)

    photos = [
        build_share_photo_item(
            id=r["id"],
            file_path=r["file_path"],
            url=f"/media/{quote(r['file_path'])}",
            thumb_small_url=f"/thumb/{quote(r['file_path'])}?size=small",
            thumb_medium_url=f"/thumb/{quote(r['file_path'])}?size=medium",
            meta=cached.get(r["file_path"], {}),
        )
        for r in rows
    ]
    return SharePhotosResponse(photos=photos, total=total, page=page)


@router.get("/{token}/og-image")
async def og_cover_image(token: str, request: Request, db=Depends(get_db)):
    """카카오톡 등 SNS 미리보기용 커버 이미지. 세션 쿠키 불필요.

    패스워드 보호 앨범은 노출하지 않음 — 제목/설명(share_spa OG 메타)은 유지하되
    커버 이미지만 차단."""
    await _check_public_rate_limit(request, db)
    link = await _get_valid_link_tracked(token, request, db)
    if link["password_hash"] is not None:
        raise HTTPException(status_code=404, detail="Cover image not available for protected album")

    async with db.execute(
        """
        SELECT a.cover_path FROM share_links sl
        JOIN albums a ON a.id = sl.album_id
        WHERE sl.token = ? AND sl.is_active = 1
        """,
        (token,),
    ) as cur:
        row = await cur.fetchone()

    cover_path = row["cover_path"] if row else None

    if not cover_path:
        async with db.execute(
            """
            SELECT ap.file_path FROM share_links sl
            JOIN album_photos ap ON ap.album_id = sl.album_id
            WHERE sl.token = ? AND sl.is_active = 1
            ORDER BY ap.sort_order, ap.id
            LIMIT 1
            """,
            (token,),
        ) as cur:
            photo_row = await cur.fetchone()
        if photo_row is None:
            raise HTTPException(status_code=404, detail="No cover image")
        cover_path = photo_row["file_path"]

    photo_root = os.path.realpath(os.getenv("PHOTO_ROOT", "./testdata/photos"))
    abs_path = _resolve_abs(cover_path, photo_root)
    _assert_within_photo_root(abs_path, photo_root)

    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="Cover image not found")

    out_path = await asyncio.get_running_loop().run_in_executor(
        None, generate_thumbnail, abs_path, "medium"
    )
    return FileResponse(out_path, media_type="image/jpeg")


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
    paths = []
    for r in rows:
        abs_path = _resolve_abs(r["file_path"], zip_root)
        _assert_within_photo_root(abs_path, zip_root)
        paths.append(abs_path)
    album_name = rows[0]["album_name"]
    safe_name = "".join(c for c in album_name if c.isalnum() or c in " _-").strip() or "album"
    encoded_name = quote(safe_name + ".zip", safe="")

    return StreamingResponse(
        zip_generator(paths),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )
