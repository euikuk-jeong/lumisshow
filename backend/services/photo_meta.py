"""photo_meta_cache 조회/적재 — admin_browse·admin_albums·admin_people·share 공용."""

import asyncio
import os
from datetime import datetime

from backend.models.database import _PHOTO_META_CACHE_VERSION
from backend.services.thumbnail import get_image_meta

_CACHE_INSERT_SQL = """
INSERT OR REPLACE INTO photo_meta_cache
    (file_path, taken_at, width, height, make, camera, software,
     shutter, aperture, iso, focal_length, shoot_mode, flash, metering, exposure_mode,
     cache_version)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_CACHE_CHUNK = 900  # SQLite host-param limit safety margin


def _photo_root() -> str:
    return os.path.realpath(os.getenv("PHOTO_ROOT", "./testdata/photos"))


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
