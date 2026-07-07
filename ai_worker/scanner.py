"""PHOTO_ROOT 증분 스캔 — 미분석/변경(mtime) 사진만 골라낸다."""

import os
import sqlite3
from typing import Iterator

from ai_worker import config


def walk_photos(root: str) -> Iterator[tuple[str, float]]:
    """(PHOTO_ROOT 상대 경로, mtime) 나열. 숨김 디렉토리(@eaDir 등)는 제외."""
    for dirpath, dirnames, filenames in os.walk(root):
        # Synology 썸네일 폴더(@eaDir), 숨김 폴더 제외
        dirnames[:] = [d for d in dirnames if not d.startswith((".", "@", "#"))]
        for name in filenames:
            if os.path.splitext(name)[1].lower() not in config.IMAGE_EXTENSIONS:
                continue
            full = os.path.join(dirpath, name)
            try:
                mtime = os.path.getmtime(full)
            except OSError:
                continue  # 스캔 중 삭제/접근 불가 파일은 건너뜀
            rel = os.path.relpath(full, root).replace("\\", "/")
            yield rel, mtime


def pending_photos(conn: sqlite3.Connection, root: str) -> list[tuple[str, float]]:
    """분석이 필요한 (상대 경로, mtime) 목록 — 신규 또는 mtime 변경분."""
    analyzed = {
        row["path"]: row["mtime"]
        for row in conn.execute("SELECT path, mtime FROM photos_analyzed")
    }
    return [
        (rel, mtime)
        for rel, mtime in walk_photos(root)
        if analyzed.get(rel) != mtime
    ]
