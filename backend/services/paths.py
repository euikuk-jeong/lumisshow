"""PHOTO_ROOT 하위 경로 resolve·containment 검증 — media·share 공용."""

import os

from fastapi import HTTPException


def resolve_abs(rel_path: str, root: str) -> str:
    if os.path.isabs(rel_path):
        return os.path.realpath(rel_path)
    return os.path.realpath(os.path.join(root, rel_path))


def assert_within_photo_root(abs_path: str, root: str) -> None:
    if abs_path != root and not abs_path.startswith(root + os.sep):
        raise HTTPException(status_code=403, detail="Access denied")
