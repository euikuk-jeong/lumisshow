import asyncio
import os
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse

from backend.models.database import get_db
from backend.models.schemas import parse_music_paths
from backend.services.auth import get_share_token_from_cookie, verify_share_session_cookie
from backend.services.music_tags import read_cover_image
from backend.services.paths import assert_within_photo_root, resolve_abs
from backend.services.thumbnail import SIZES, generate_thumbnail, is_video

router = APIRouter(tags=["media"])

_COOKIE = "share_session"

# token → (set[rel_path], expires_at) — 앨범 소속 검증 결과 단기 캐시
_album_paths_cache: dict[str, tuple[set[str], float]] = {}
_ALBUM_CACHE_TTL = 30  # 초: 링크 비활성화 반영 최대 지연


def _photo_root() -> str:
    return os.path.realpath(os.getenv("PHOTO_ROOT", "./testdata/photos"))


def _to_relative(file_path: str, root: str) -> str:
    if os.path.isabs(file_path):
        try:
            return os.path.relpath(os.path.realpath(file_path), root).replace("\\", "/")
        except ValueError:
            return file_path
    return file_path.replace("\\", "/")


def _evict_stale_cache() -> None:
    now = time.time()
    stale = [k for k, (_, exp) in _album_paths_cache.items() if now >= exp]
    for k in stale:
        del _album_paths_cache[k]
    # 캐시 항목 상한선
    if len(_album_paths_cache) > 500:
        oldest = min(_album_paths_cache, key=lambda k: _album_paths_cache[k][1])
        del _album_paths_cache[oldest]


async def _get_album_paths(token: str, db) -> set[str]:
    """토큰에 속한 유효한 file_path 집합 반환. 캐시 우선 조회."""
    now = time.time()
    entry = _album_paths_cache.get(token)
    if entry and now < entry[1]:
        return entry[0]

    _evict_stale_cache()
    async with db.execute(
        """
        SELECT ap.file_path FROM share_links sl
        JOIN album_photos ap ON ap.album_id = sl.album_id
        WHERE sl.token = ? AND sl.is_active = 1
          AND (sl.expires_at IS NULL OR sl.expires_at > datetime('now'))
        """,
        (token,),
    ) as cur:
        rows = await cur.fetchall()

    paths = {r["file_path"] for r in rows}
    _album_paths_cache[token] = (paths, now + _ALBUM_CACHE_TTL)
    return paths


async def _verify_file_in_album(token: str, file_path: str, db) -> None:
    paths = await _get_album_paths(token, db)
    if file_path not in paths:
        raise HTTPException(status_code=403, detail="Access denied")


@router.get("/thumb/{file_path:path}")
async def serve_thumb(file_path: str, request: Request, size: str = "small", db=Depends(get_db)):
    if size not in SIZES:
        raise HTTPException(status_code=400, detail=f"Invalid size. Use: {', '.join(SIZES)}")
    root = _photo_root()
    token = get_share_token_from_cookie(request.cookies.get(_COOKIE))
    rel = _to_relative(file_path, root)
    await _verify_file_in_album(token, rel, db)
    abs_path = resolve_abs(rel, root)
    assert_within_photo_root(abs_path, root)
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="File not found")
    out_path = await asyncio.get_running_loop().run_in_executor(
        None, generate_thumbnail, abs_path, size
    )
    return FileResponse(out_path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/media/{file_path:path}")
async def serve_media(file_path: str, request: Request, db=Depends(get_db)):
    root = _photo_root()
    token = get_share_token_from_cookie(request.cookies.get(_COOKIE))
    rel = _to_relative(file_path, root)
    await _verify_file_in_album(token, rel, db)
    abs_path = resolve_abs(rel, root)
    assert_within_photo_root(abs_path, root)
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="File not found")
    if is_video(abs_path):
        # <video> 태그 스트리밍용 — attachment 헤더가 붙으면 일부 브라우저가
        # 재생 대신 다운로드로 취급할 수 있어 inline으로 서빙한다.
        return FileResponse(abs_path, filename=os.path.basename(abs_path), content_disposition_type="inline")
    return FileResponse(abs_path, filename=os.path.basename(abs_path))


def _music_dir() -> str:
    return os.path.join(os.getenv("DATA_DIR", "./testdata/data"), "music")


async def _resolve_music_track(token: str, index: int, request: Request, db) -> str:
    verify_share_session_cookie(token, request.cookies.get(_COOKIE))
    async with db.execute(
        """
        SELECT a.music_path FROM share_links sl
        JOIN albums a ON a.id = sl.album_id
        WHERE sl.token = ? AND sl.is_active = 1
          AND (sl.expires_at IS NULL OR sl.expires_at > datetime('now'))
        """,
        (token,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Music not found")
    music_paths = parse_music_paths(row["music_path"])
    if not music_paths or index >= len(music_paths):
        raise HTTPException(status_code=404, detail="Track not found")
    allowed_dir = os.path.realpath(_music_dir())
    resolved = os.path.realpath(music_paths[index])
    if resolved != allowed_dir and not resolved.startswith(allowed_dir + os.sep):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.isfile(resolved):
        raise HTTPException(status_code=404, detail="Music file not found")
    return resolved


@router.get("/music/{token}")
async def serve_music(token: str, request: Request, index: int = Query(default=0, ge=0), db=Depends(get_db)):
    resolved = await _resolve_music_track(token, index, request, db)
    return FileResponse(resolved)


@router.get("/music/{token}/cover")
async def serve_music_cover(token: str, request: Request, index: int = Query(default=0, ge=0), db=Depends(get_db)):
    resolved = await _resolve_music_track(token, index, request, db)
    cover = read_cover_image(resolved)
    if cover is None:
        raise HTTPException(status_code=404, detail="Cover not found")
    data, mime = cover
    return Response(content=data, media_type=mime, headers={"Cache-Control": "private, max-age=86400"})
