"""PHOTO_ROOT 하위 경로 resolve·containment 검증 — media·share 공용."""

import os
from pathlib import Path

from fastapi import HTTPException

from backend.services.thumbnail import IMAGE_EXTENSIONS

_PHOTO_SKIP_PREFIXES = (".", "@", "#")


def resolve_abs(rel_path: str, root: str) -> str:
    if os.path.isabs(rel_path):
        return os.path.realpath(rel_path)
    return os.path.realpath(os.path.join(root, rel_path))


def assert_within_photo_root(abs_path: str, root: str) -> None:
    if abs_path != root and not abs_path.startswith(root + os.sep):
        raise HTTPException(status_code=403, detail="Access denied")


def build_filename_index(photo_root: str) -> dict[str, list[str]]:
    """PHOTO_ROOT 전체를 스캔해 {파일명(소문자) -> [상대경로]} 인덱스 반환.
    파일명 기반 경로 복구(rename/move 대응)에 admin_albums·admin_people이 공용으로 사용."""
    index: dict[str, list[str]] = {}
    for dirpath, dirnames, filenames in os.walk(photo_root):
        dirnames[:] = [d for d in dirnames if not d.startswith(_PHOTO_SKIP_PREFIXES)]
        for fname in filenames:
            if fname.startswith(_PHOTO_SKIP_PREFIXES):
                continue
            if Path(fname).suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            rel = os.path.relpath(os.path.join(dirpath, fname), photo_root).replace("\\", "/")
            index.setdefault(fname.lower(), []).append(rel)
    return index
