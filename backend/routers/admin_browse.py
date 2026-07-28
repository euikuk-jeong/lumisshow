import asyncio
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from backend.models.database import get_db
from backend.models.schemas import BrowseResponse, FolderItem, PhotoItem, SearchResponse

_AUDIO_EXTENSIONS = {'.mp3', '.flac', '.ogg', '.m4a', '.wav', '.aac', '.opus'}
from backend.services.auth import admin_image_auth, get_current_admin
from backend.services.photo_meta import load_photo_meta
from backend.services.settings import get_settings
from backend.services.thumbnail import IMAGE_EXTENSIONS, generate_thumbnail

router = APIRouter(prefix="/api/admin", tags=["admin-browse"])

# Synology NAS 시스템 폴더/파일 접두사: @eaDir, @tmp, #recycle, #snapshot 등
_SKIP_PREFIXES = (".", "@", "#")


def _is_hidden(name: str) -> bool:
    return name.startswith(_SKIP_PREFIXES)


def _is_path_hidden(rel: str, hidden_paths: list[str]) -> bool:
    """rel이 hidden_paths 중 하나와 같거나 그 하위 경로이면 True."""
    for h in hidden_paths:
        if rel == h or rel.startswith(h + "/"):
            return True
    return False


def _photo_root() -> str:
    return os.path.realpath(os.getenv("PHOTO_ROOT", "./testdata/photos"))


def _safe_dir(rel: str, root: str | None = None) -> str:
    """rel 경로를 PHOTO_ROOT 하위로 한정. 벗어나면 400."""
    if root is None:
        root = _photo_root()
    resolved = os.path.realpath(os.path.join(root, rel.lstrip("/\\")))
    if resolved != root and not resolved.startswith(root + os.sep):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not os.path.isdir(resolved):
        raise HTTPException(status_code=404, detail="Directory not found")
    return resolved


def _scan_dir_basic(real_path: str, root: str, hidden_paths: list[str]) -> tuple[list[FolderItem], list[tuple[str, str, int]]]:
    """폴더 목록과 기본 사진 정보(full_path, name, size)를 반환. EXIF 없음."""
    folders: list[FolderItem] = []
    basics: list[tuple[str, str, int]] = []
    with os.scandir(real_path) as entries:
        for entry in sorted(entries, key=lambda e: e.name.lower()):
            if _is_hidden(entry.name):
                continue
            if entry.is_dir(follow_symlinks=False):
                rel = os.path.relpath(entry.path, root).replace("\\", "/")
                if _is_path_hidden(rel, hidden_paths):
                    continue
                try:
                    child_count = sum(1 for n in os.listdir(entry.path) if not _is_hidden(n))
                except PermissionError:
                    child_count = 0
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
    hidden_paths: list[str],
) -> list[tuple[str, str, int]]:
    """파일명 필터로 사진을 재귀 탐색. EXIF 없이 (full_path, name, size) 반환."""
    results: list[tuple[str, str, int]] = []
    for dirpath, dirnames, filenames in os.walk(start_dir):
        dirnames[:] = sorted(
            d for d in dirnames
            if not _is_hidden(d)
            and not _is_path_hidden(os.path.relpath(os.path.join(dirpath, d), root).replace("\\", "/"), hidden_paths)
        )
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


# search()의 전체 트리 walk 결과를 짧게 캐싱 — 검색어(q)만 바뀌는 반복 호출마다
# NAS 전체를 재순회하지 않도록 q 필터 없이(전체) 캐싱하고 q는 캐시 조회 후 적용
_WALK_CACHE_TTL = 30  # 초
_walk_cache: dict[tuple[str, tuple[str, ...]], tuple[list[tuple[str, str, int]], float]] = {}


def _evict_stale_walk_cache() -> None:
    now = time.time()
    stale = [k for k, (_, exp) in _walk_cache.items() if now >= exp]
    for k in stale:
        del _walk_cache[k]
    if len(_walk_cache) > 100:
        oldest = min(_walk_cache, key=lambda k: _walk_cache[k][1])
        del _walk_cache[oldest]


def _walk_all_photos_basic_cached(
    start_dir: str, root: str, hidden_paths: list[str]
) -> list[tuple[str, str, int]]:
    key = (start_dir, tuple(hidden_paths))
    now = time.time()
    entry = _walk_cache.get(key)
    if entry and now < entry[1]:
        return entry[0]

    _evict_stale_walk_cache()
    results = _walk_photos_basic(start_dir, root, None, hidden_paths)
    _walk_cache[key] = (results, now + _WALK_CACHE_TTL)
    return results


async def _enrich_photos(
    basic_items: list[tuple[str, str, int]],
    root: str,
    db,
) -> list[PhotoItem]:
    """basic_items의 각 사진에 EXIF 메타데이터를 추가. photo_meta_cache 활용 (IN 쿼리)."""
    if not basic_items:
        return []

    rel_map = {fp: os.path.relpath(fp, root).replace("\\", "/") for fp, _, _ in basic_items}
    meta_by_rel = await load_photo_meta(list(rel_map.values()), db)

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
    root = _photo_root()
    settings = await get_settings(db)
    hidden_paths = settings.get("browse_hidden_paths", [])
    real_path = _safe_dir(path, root)
    folders, basics = await asyncio.to_thread(_scan_dir_basic, real_path, root, hidden_paths)
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
    settings = await get_settings(db)
    hidden_paths = settings.get("browse_hidden_paths", [])
    start_dir = _safe_dir(folder, root) if folder else root

    df = datetime.strptime(date_from, "%Y-%m-%d") if date_from else None
    dt = (
        datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        if date_to
        else None
    )

    all_basics = await asyncio.to_thread(_walk_all_photos_basic_cached, start_dir, root, hidden_paths)
    if q:
        ql = q.lower()
        basics = [b for b in all_basics if ql in b[1].lower()]
    else:
        basics = all_basics

    if df or dt:
        # 날짜 필터: 전체 EXIF 필요 → 먼저 enrich, 필터 후 페이지네이션
        all_items = await _enrich_photos(basics, root, db)
        filtered = [
            item for item in all_items
            if (not df or (item.taken_at and item.taken_at >= df))
            and (not dt or (item.taken_at and item.taken_at <= dt))
        ]
        total = len(filtered)
        offset = (page - 1) * size
        return SearchResponse(items=filtered[offset: offset + size], total=total, page=page)
    else:
        # 날짜 필터 없음: 페이지네이션 후 enrich (해당 페이지만 EXIF 로드)
        total = len(basics)
        offset = (page - 1) * size
        page_basics = basics[offset: offset + size]
        items = await _enrich_photos(page_basics, root, db)
        return SearchResponse(items=items, total=total, page=page)


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


@router.get("/path-exists")
async def path_exists(
    path: str = Query(...),
    _: str = Depends(get_current_admin),
):
    if not path or not path.strip("/\\"):
        return {"exists": False}
    root = _photo_root()
    resolved = os.path.realpath(os.path.join(root, path.lstrip("/\\")))
    return {"exists": resolved.startswith(root + os.sep) and os.path.isdir(resolved)}


@router.get("/thumb")
async def admin_thumb(
    path: str = Query(...),
    size: str = Query(default="small"),
    _: str = Depends(admin_image_auth),
):
    if size not in ("small", "medium", "large"):
        raise HTTPException(status_code=400, detail="size must be 'small', 'medium', or 'large'")
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
    return FileResponse(out, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/photo")
async def admin_photo(
    path: str = Query(...),
    _: str = Depends(admin_image_auth),
):
    root = _photo_root()
    if os.path.isabs(path):
        full_path = os.path.realpath(path)
    else:
        full_path = os.path.realpath(os.path.join(root, path.lstrip("/\\")))
    if full_path != root and not full_path.startswith(root + os.sep):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(full_path)
