import asyncio
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from backend.models.database import get_db
from backend.services.auth import get_share_token_from_cookie, verify_share_session_cookie
from backend.services.thumbnail import SIZES, generate_thumbnail

router = APIRouter(tags=["media"])

_COOKIE = "share_session"


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
    await _verify_file_in_album(token, file_path, db)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    out_path = await asyncio.get_running_loop().run_in_executor(
        None, generate_thumbnail, file_path, size
    )
    return FileResponse(out_path, media_type="image/jpeg")


@router.get("/media/{file_path:path}")
async def serve_media(file_path: str, request: Request, db=Depends(get_db)):
    token = get_share_token_from_cookie(request.cookies.get(_COOKIE))
    await _verify_file_in_album(token, file_path, db)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)


def _music_dir() -> str:
    return os.path.join(os.getenv("DATA_DIR", "./testdata/data"), "music")


@router.get("/music/{token}")
async def serve_music(token: str, request: Request, db=Depends(get_db)):
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
    if row is None or row["music_path"] is None:
        raise HTTPException(status_code=404, detail="Music not found")
    music_path = row["music_path"]
    allowed_dir = os.path.realpath(_music_dir())
    resolved = os.path.realpath(music_path)
    if resolved != allowed_dir and not resolved.startswith(allowed_dir + os.sep):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.isfile(resolved):
        raise HTTPException(status_code=404, detail="Music file not found")
    return FileResponse(resolved)
