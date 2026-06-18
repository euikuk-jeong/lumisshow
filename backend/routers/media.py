import asyncio
import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from backend.models.database import get_db
from backend.models.schemas import parse_music_paths
from backend.services.auth import get_share_token_from_cookie, verify_share_session_cookie
from backend.services.thumbnail import SIZES, generate_thumbnail

router = APIRouter(tags=["media"])

_COOKIE = "share_session"


def _photo_root() -> str:
    return os.path.realpath(os.getenv("PHOTO_ROOT", "./testdata/photos"))


def _to_relative(file_path: str) -> str:
    """URL로 받은 경로(절대 또는 상대)를 DB에 저장된 상대 경로 형식으로 정규화."""
    root = _photo_root()
    if os.path.isabs(file_path):
        try:
            return os.path.relpath(os.path.realpath(file_path), root).replace("\\", "/")
        except ValueError:
            return file_path
    return file_path.replace("\\", "/")


def _resolve_abs(rel_path: str) -> str:
    """상대 경로를 PHOTO_ROOT 기준 절대 경로로 변환."""
    if os.path.isabs(rel_path):
        return os.path.realpath(rel_path)
    return os.path.realpath(os.path.join(_photo_root(), rel_path))


def _assert_within_photo_root(abs_path: str) -> None:
    root = _photo_root()
    if abs_path != root and not abs_path.startswith(root + os.sep):
        raise HTTPException(status_code=403, detail="Access denied")


async def _verify_file_in_album(token: str, file_path: str, db) -> None:
    """file_path가 해당 토큰 앨범에 속하고 링크가 유효한지 검증. 실패 시 403."""
    async with db.execute(
        """
        SELECT 1 FROM share_links sl
        JOIN album_photos ap ON ap.album_id = sl.album_id
        WHERE sl.token = ? AND sl.is_active = 1
          AND (sl.expires_at IS NULL OR sl.expires_at > datetime('now'))
          AND ap.file_path = ?
        """,
        (token, file_path),
    ) as cur:
        if await cur.fetchone() is None:
            raise HTTPException(status_code=403, detail="Access denied")


@router.get("/thumb/{file_path:path}")
async def serve_thumb(file_path: str, request: Request, size: str = "small", db=Depends(get_db)):
    if size not in SIZES:
        raise HTTPException(status_code=400, detail=f"Invalid size. Use: {', '.join(SIZES)}")
    token = get_share_token_from_cookie(request.cookies.get(_COOKIE))
    rel = _to_relative(file_path)
    await _verify_file_in_album(token, rel, db)
    abs_path = _resolve_abs(rel)
    _assert_within_photo_root(abs_path)
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="File not found")
    out_path = await asyncio.get_running_loop().run_in_executor(
        None, generate_thumbnail, abs_path, size
    )
    return FileResponse(out_path, media_type="image/jpeg")


@router.get("/media/{file_path:path}")
async def serve_media(file_path: str, request: Request, db=Depends(get_db)):
    token = get_share_token_from_cookie(request.cookies.get(_COOKIE))
    rel = _to_relative(file_path)
    await _verify_file_in_album(token, rel, db)
    abs_path = _resolve_abs(rel)
    _assert_within_photo_root(abs_path)
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(abs_path, filename=os.path.basename(abs_path))


def _music_dir() -> str:
    return os.path.join(os.getenv("DATA_DIR", "./testdata/data"), "music")


@router.get("/music/{token}")
async def serve_music(token: str, request: Request, index: int = Query(default=0, ge=0), db=Depends(get_db)):
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
    return FileResponse(resolved)
