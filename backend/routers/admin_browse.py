import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from backend.models.schemas import BrowseResponse, FolderItem, PhotoItem, SearchResponse
from backend.services.auth import get_current_admin
from backend.services.thumbnail import IMAGE_EXTENSIONS, generate_thumbnail, get_image_meta

router = APIRouter(prefix="/api/admin", tags=["admin-browse"])


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


def _build_photo_item(full_path: str, root: str) -> PhotoItem:
    rel = os.path.relpath(full_path, root).replace("\\", "/")
    stat = os.stat(full_path)
    meta = get_image_meta(full_path)
    return PhotoItem(
        path=rel,
        name=os.path.basename(full_path),
        size=stat.st_size,
        taken_at=meta["taken_at"],
        width=meta["width"],
        height=meta["height"],
        thumb_url=f"/api/admin/thumb?path={quote(rel)}&size=small",
    )


def _scan_dir(real_path: str, root: str) -> tuple[list[FolderItem], list[PhotoItem]]:
    folders: list[FolderItem] = []
    photos: list[PhotoItem] = []
    with os.scandir(real_path) as entries:
        for entry in sorted(entries, key=lambda e: e.name.lower()):
            if entry.name.startswith("."):
                continue
            if entry.is_dir(follow_symlinks=False):
                try:
                    child_count = sum(
                        1 for e in os.scandir(entry.path) if not e.name.startswith(".")
                    )
                except PermissionError:
                    child_count = 0
                rel = os.path.relpath(entry.path, root).replace("\\", "/")
                folders.append(FolderItem(path=rel, name=entry.name, child_count=child_count))
            elif entry.is_file():
                if Path(entry.name).suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                photos.append(_build_photo_item(entry.path, root))
    return folders, photos


def _walk_photos(
    start_dir: str,
    root: str,
    q: Optional[str],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
) -> list[PhotoItem]:
    results: list[PhotoItem] = []
    for dirpath, dirnames, filenames in os.walk(start_dir):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for fname in sorted(filenames):
            if fname.startswith("."):
                continue
            if Path(fname).suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            if q and q.lower() not in fname.lower():
                continue
            full_path = os.path.join(dirpath, fname)
            item = _build_photo_item(full_path, root)
            if date_from and (not item.taken_at or item.taken_at < date_from):
                continue
            if date_to and (not item.taken_at or item.taken_at > date_to):
                continue
            results.append(item)
    return results


# ── 엔드포인트 ────────────────────────────────────────────────────────────────

@router.get("/browse", response_model=BrowseResponse)
async def browse(
    path: str = Query(default=""),
    _: str = Depends(get_current_admin),
):
    real_path = _safe_dir(path)
    root = _photo_root()
    folders, photos = await asyncio.to_thread(_scan_dir, real_path, root)
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
):
    root = _photo_root()
    start_dir = _safe_dir(folder) if folder else root

    df = datetime.strptime(date_from, "%Y-%m-%d") if date_from else None
    dt = (
        datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        if date_to
        else None
    )

    all_items = await asyncio.to_thread(_walk_photos, start_dir, root, q, df, dt)
    total = len(all_items)
    offset = (page - 1) * size
    return SearchResponse(items=all_items[offset : offset + size], total=total, page=page)


@router.get("/thumb")
async def admin_thumb(
    path: str = Query(...),
    size: str = Query(default="small"),
    _: str = Depends(get_current_admin),
):
    if size not in ("small", "medium"):
        raise HTTPException(status_code=400, detail="size must be 'small' or 'medium'")
    root = _photo_root()
    full_path = os.path.realpath(os.path.join(root, path.lstrip("/\\")))
    if full_path != root and not full_path.startswith(root + os.sep):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    out = await asyncio.to_thread(generate_thumbnail, full_path, size)
    return FileResponse(out, media_type="image/jpeg")
