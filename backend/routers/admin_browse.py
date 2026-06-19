import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.models.database import get_db
from backend.models.schemas import BrowseResponse, FolderItem, PhotoItem, SearchResponse

_AUDIO_EXTENSIONS = {'.mp3', '.flac', '.ogg', '.m4a', '.wav', '.aac', '.opus'}
from backend.services.auth import get_current_admin, verify_admin_token
from backend.services.thumbnail import IMAGE_EXTENSIONS, generate_thumbnail, get_image_meta

_bearer_optional = HTTPBearer(auto_error=False)
_ADMIN_IMG_COOKIE = "admin_img_session"


async def _admin_image_auth(
    request: Request,
    cred: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_optional),
) -> str:
    """이미지 서빙용: Bearer 헤더 또는 admin_img_session 쿠키로 인증."""
    raw = (cred.credentials if cred else None) or request.cookies.get(_ADMIN_IMG_COOKIE)
    if raw and verify_admin_token(raw):
        return "admin"
    raise HTTPException(status_code=401, detail="Admin authentication required")

router = APIRouter(prefix="/api/admin", tags=["admin-browse"])

# Synology NAS 시스템 폴더/파일 접두사: @eaDir, @tmp, #recycle, #snapshot 등
_SKIP_PREFIXES = (".", "@", "#")


def _is_hidden(name: str) -> bool:
    return name.startswith(_SKIP_PREFIXES)


def _photo_root() -> str:
    return os.path.realpath(os.getenv("PHOTO_ROOT", "./testdata/photos"))


def _safe_dir(rel: str) -> str:
    """rel 경로를 PHOTO_ROOT 하위로 한정. 벗어나면 400."""
    root = _photo_root()
    resolved = os.path.realpath(os.path.join(root, rel.lstrip("/\\")))
    if resolved != root and not resolved.startswith(root + os.sep):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not os.path.isdir(resolved):
        raise HTTPException(status_code=404, detail="Directory not found")
    return resolved


def _scan_dir_basic(real_path: str, root: str) -> tuple[list[FolderItem], list[tuple[str, str, int]]]:
    """폴더 목록과 기본 사진 정보(full_path, name, size)를 반환. EXIF 없음."""
    folders: list[FolderItem] = []
    basics: list[tuple[str, str, int]] = []
    with os.scandir(real_path) as entries:
        for entry in sorted(entries, key=lambda e: e.name.lower()):
            if _is_hidden(entry.name):
                continue
            if entry.is_dir(follow_symlinks=False):
                try:
                    child_count = sum(
                        1 for e in os.scandir(entry.path) if not _is_hidden(e.name)
                    )
                except PermissionError:
                    child_count = 0
                rel = os.path.relpath(entry.path, root).replace("\\", "/")
                folders.append(FolderItem(path=rel, name=entry.name, child_count=child_count))
            elif entry.is_file():
                if Path(entry.name).suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                stat = os.stat(entry.path)
                basics.append((entry.path, entry.name, stat.st_size))
    return folders, basics


def _walk_photos_basic(
    start_dir: str,
    root: str,
    q: Optional[str],
) -> list[tuple[str, str, int]]:
    """파일명 필터로 사진을 재귀 탐색. EXIF 없이 (full_path, name, size) 반환."""
    results: list[tuple[str, str, int]] = []
    for dirpath, dirnames, filenames in os.walk(start_dir):
        dirnames[:] = sorted(d for d in dirnames if not _is_hidden(d))
        for fname in sorted(filenames):
            if _is_hidden(fname):
                continue
            if Path(fname).suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            if q and q.lower() not in fname.lower():
                continue
            full_path = os.path.join(dirpath, fname)
            stat = os.stat(full_path)
            results.append((full_path, fname, stat.st_size))
    return results


async def _enrich_photos(
    basic_items: list[tuple[str, str, int]],
    root: str,
    db,
) -> list[PhotoItem]:
    """basic_items의 각 사진에 EXIF 메타데이터를 추가. photo_meta_cache 활용."""
    if not basic_items:
        return []

    rel_map = {fp: os.path.relpath(fp, root).replace("\\", "/") for fp, _, _ in basic_items}

    meta_by_rel: dict[str, dict] = {}
    uncached: list[tuple[str, str]] = []  # (rel, full_path)

    for full_path, _, _ in basic_items:
        rel = rel_map[full_path]
        async with db.execute(
            "SELECT taken_at, width, height FROM photo_meta_cache WHERE file_path = ?", (rel,)
        ) as cur:
            row = await cur.fetchone()
        if row:
            taken_at = datetime.fromisoformat(row["taken_at"]) if row["taken_at"] else None
            meta_by_rel[rel] = {"taken_at": taken_at, "width": row["width"], "height": row["height"]}
        else:
            uncached.append((rel, full_path))

    if uncached:
        metas = await asyncio.gather(*[
            asyncio.to_thread(get_image_meta, fp) for _, fp in uncached
        ])
        inserts = []
        for (rel, _), meta in zip(uncached, metas):
            meta_by_rel[rel] = meta
            inserts.append((
                rel,
                meta["taken_at"].isoformat() if meta.get("taken_at") else None,
                meta.get("width"),
                meta.get("height"),
            ))
        await db.executemany(
            "INSERT OR REPLACE INTO photo_meta_cache (file_path, taken_at, width, height) VALUES (?, ?, ?, ?)",
            inserts,
        )
        await db.commit()

    items = []
    for full_path, name, size in basic_items:
        rel = rel_map[full_path]
        meta = meta_by_rel.get(rel, {})
        items.append(PhotoItem(
            path=rel,
            name=name,
            size=size,
            taken_at=meta.get("taken_at"),
            width=meta.get("width"),
            height=meta.get("height"),
            thumb_url=f"/api/admin/thumb?path={quote(rel)}&size=small",
        ))
    return items


# ── 엔드포인트 ────────────────────────────────────────────────────────────────

@router.get("/browse", response_model=BrowseResponse)
async def browse(
    path: str = Query(default=""),
    _: str = Depends(get_current_admin),
    db=Depends(get_db),
):
    real_path = _safe_dir(path)
    root = _photo_root()
    folders, basics = await asyncio.to_thread(_scan_dir_basic, real_path, root)
    photos = await _enrich_photos(basics, root, db)
    return BrowseResponse(folders=folders, photos=photos)


@router.get("/search", response_model=SearchResponse)
async def search(
    q: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    folder: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=100, ge=1, le=500),
    _: str = Depends(get_current_admin),
    db=Depends(get_db),
):
    root = _photo_root()
    start_dir = _safe_dir(folder) if folder else root

    df = datetime.strptime(date_from, "%Y-%m-%d") if date_from else None
    dt = (
        datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        if date_to
        else None
    )

    basics = await asyncio.to_thread(_walk_photos_basic, start_dir, root, q)
    all_items = await _enrich_photos(basics, root, db)

    if df or dt:
        filtered = []
        for item in all_items:
            if df and (not item.taken_at or item.taken_at < df):
                continue
            if dt and (not item.taken_at or item.taken_at > dt):
                continue
            filtered.append(item)
        all_items = filtered

    total = len(all_items)
    offset = (page - 1) * size
    return SearchResponse(items=all_items[offset: offset + size], total=total, page=page)


@router.get("/music")
async def list_music(_: str = Depends(get_current_admin)):
    music_dir = os.path.join(os.getenv("DATA_DIR", "./testdata/data"), "music")
    if not os.path.isdir(music_dir):
        return {"files": []}
    files = []
    for dirpath, dirnames, filenames in os.walk(music_dir):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for fname in sorted(filenames):
            if fname.startswith("."):
                continue
            if Path(fname).suffix.lower() not in _AUDIO_EXTENSIONS:
                continue
            full_path = os.path.join(dirpath, fname)
            rel = os.path.relpath(full_path, music_dir).replace("\\", "/")
            files.append({"path": full_path, "name": fname, "rel": rel})
    return {"files": files}


@router.get("/thumb")
async def admin_thumb(
    path: str = Query(...),
    size: str = Query(default="small"),
    _: str = Depends(_admin_image_auth),
):
    if size not in ("small", "medium"):
        raise HTTPException(status_code=400, detail="size must be 'small' or 'medium'")
    root = _photo_root()
    if os.path.isabs(path):
        full_path = os.path.realpath(path)
    else:
        full_path = os.path.realpath(os.path.join(root, path.lstrip("/\\")))
    if full_path != root and not full_path.startswith(root + os.sep):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    out = await asyncio.to_thread(generate_thumbnail, full_path, size)
    return FileResponse(out, media_type="image/jpeg")
