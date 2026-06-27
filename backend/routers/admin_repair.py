import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, Depends

from backend.models.database import get_db
from backend.routers.admin_browse import _SKIP_PREFIXES
from backend.services.auth import get_current_admin
from backend.services.thumbnail import IMAGE_EXTENSIONS

router = APIRouter(prefix="/api/admin", tags=["admin-repair"])


def _build_filename_index(photo_root: str) -> dict[str, list[str]]:
    """PHOTO_ROOT 전체를 스캔해 {파일명(소문자) -> [상대경로]} 인덱스 반환."""
    index: dict[str, list[str]] = {}
    for dirpath, dirnames, filenames in os.walk(photo_root):
        dirnames[:] = [d for d in dirnames if not d.startswith(_SKIP_PREFIXES)]
        for fname in filenames:
            if fname.startswith(_SKIP_PREFIXES):
                continue
            if Path(fname).suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            abs_path = os.path.join(dirpath, fname)
            rel = os.path.relpath(abs_path, photo_root).replace("\\", "/")
            index.setdefault(fname.lower(), []).append(rel)
    return index


@router.post("/repair-paths")
async def repair_paths(
    _: str = Depends(get_current_admin),
    db=Depends(get_db),
):
    """깨진 앨범 사진 경로를 파일명 기반으로 자동 복구."""
    photo_root = os.path.realpath(os.getenv("PHOTO_ROOT", "./testdata/photos"))

    # 1. DB에 저장된 모든 고유 경로 수집
    async with db.execute("SELECT DISTINCT file_path FROM album_photos") as cur:
        all_paths = [row[0] for row in await cur.fetchall()]

    # 2. 깨진 경로 파악 (파일이 실제로 없는 경우)
    broken = [
        p for p in all_paths
        if not os.path.isfile(os.path.join(photo_root, p))
    ]
    total_checked = len(all_paths)

    if not broken:
        return {"total_checked": total_checked, "fixed": [], "ambiguous": [], "not_found": []}

    # 3. PHOTO_ROOT 전체 스캔으로 파일명 인덱스 빌드
    index = await asyncio.to_thread(_build_filename_index, photo_root)

    fixed = []
    ambiguous = []
    not_found = []

    for old_path in broken:
        basename = os.path.basename(old_path).lower()
        candidates = index.get(basename, [])

        if len(candidates) == 1:
            new_path = candidates[0]
            # 같은 앨범에 new_path가 이미 존재하면 중복 방지를 위해 old 행 삭제
            await db.execute(
                """DELETE FROM album_photos
                   WHERE file_path = ? AND EXISTS (
                       SELECT 1 FROM album_photos a2
                       WHERE a2.album_id = album_photos.album_id AND a2.file_path = ?
                   )""",
                (old_path, new_path),
            )
            await db.execute(
                "UPDATE album_photos SET file_path = ? WHERE file_path = ?",
                (new_path, old_path),
            )
            # albums.cover_path도 동일하게 수정
            await db.execute(
                "UPDATE albums SET cover_path = ? WHERE cover_path = ?",
                (new_path, old_path),
            )
            fixed.append({"old_path": old_path, "new_path": new_path})
        elif len(candidates) > 1:
            ambiguous.append({"old_path": old_path, "candidates": sorted(candidates)})
        else:
            not_found.append(old_path)

    await db.commit()
    return {
        "total_checked": total_checked,
        "fixed": fixed,
        "ambiguous": ambiguous,
        "not_found": not_found,
    }
