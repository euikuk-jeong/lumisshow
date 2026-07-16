import asyncio
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.models.database import _PHOTO_META_CACHE_VERSION, get_db
from backend.models.schemas import BrowseResponse, FolderItem, PhotoItem, SearchResponse
from backend.routers.admin_settings import get_settings

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


_CACHE_INSERT_SQL = """
INSERT OR REPLACE INTO photo_meta_cache
    (file_path, taken_at, width, height, make, camera, software,
     shutter, aperture, iso, focal_length, shoot_mode, flash, metering, exposure_mode,
     cache_version)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_CACHE_CHUNK = 900  # SQLite host-param limit safety margin


def _meta_to_row(rel: str, meta: dict) -> tuple:
    return (
        rel,
        meta["taken_at"].isoformat() if meta.get("taken_at") else None,
        meta.get("width"),
        meta.get("height"),
        meta.get("make"),
        meta.get("camera"),
        meta.get("software"),
        meta.get("shutter"),
        meta.get("aperture"),
        meta.get("iso"),
        meta.get("focal_length"),
        meta.get("shoot_mode"),
        meta.get("flash"),
        meta.get("metering"),
        meta.get("exposure_mode"),
        _PHOTO_META_CACHE_VERSION,
    )


def _row_to_meta(row) -> dict:
    taken_at = datetime.fromisoformat(row["taken_at"]) if row["taken_at"] else None
    return {
        "taken_at": taken_at,
        "width": row["width"],
        "height": row["height"],
        "make": row["make"],
        "camera": row["camera"],
        "software": row["software"],
        "shutter": row["shutter"],
        "aperture": row["aperture"],
        "iso": row["iso"],
        "focal_length": row["focal_length"],
        "shoot_mode": row["shoot_mode"],
        "flash": row["flash"],
        "metering": row["metering"],
        "exposure_mode": row["exposure_mode"],
    }


_EXIF_READ_CONCURRENCY = int(os.getenv("EXIF_READ_CONCURRENCY", "8"))
_exif_read_semaphore = asyncio.Semaphore(_EXIF_READ_CONCURRENCY)


async def _read_meta_limited(abs_path: str) -> dict:
    async with _exif_read_semaphore:
        return await asyncio.to_thread(get_image_meta, abs_path)


async def load_photo_meta(rels: list[str], db) -> dict[str, dict]:
    """rel 경로 목록의 EXIF 메타를 photo_meta_cache에서 일괄 조회, 미스는 파일에서 읽어 캐시.

    미스 읽기는 세마포어(EXIF_READ_CONCURRENCY)로 동시 실행 개수를 제한 —
    캐시 미스가 대량(예: search 날짜 필터 첫 조회)이어도 NAS I/O가 한꺼번에
    몰리지 않도록 한다."""
    root = _photo_root()
    meta_by_rel: dict[str, dict] = {}

    for i in range(0, len(rels), _CACHE_CHUNK):
        chunk = rels[i:i + _CACHE_CHUNK]
        placeholders = ",".join("?" * len(chunk))
        async with db.execute(
            f"SELECT * FROM photo_meta_cache WHERE cache_version >= ? AND file_path IN ({placeholders})",
            [_PHOTO_META_CACHE_VERSION] + chunk,
        ) as cur:
            for row in await cur.fetchall():
                meta_by_rel[row["file_path"]] = _row_to_meta(row)

    uncached = [r for r in rels if r not in meta_by_rel]
    if uncached:
        def _abs(p: str) -> str:
            return p if os.path.isabs(p) else os.path.join(root, p)

        metas = await asyncio.gather(*[
            _read_meta_limited(_abs(r)) for r in uncached
        ])
        for rel, meta in zip(uncached, metas):
            meta_by_rel[rel] = meta
        # 읽기 성공(width not None)한 경우만 캐시 저장 — 실패 결과는 저장 안 해 다음 요청에 재시도
        inserts = [_meta_to_row(rel, meta) for rel, meta in zip(uncached, metas)
                   if meta.get("width") is not None]
        if inserts:
            await db.executemany(_CACHE_INSERT_SQL, inserts)
        await db.commit()
    return meta_by_rel


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
    return FileResponse(out, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/photo")
async def admin_photo(
    path: str = Query(...),
    _: str = Depends(_admin_image_auth),
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
