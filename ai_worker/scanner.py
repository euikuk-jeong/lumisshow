"""PHOTO_ROOT 증분 스캔 — 미분석/변경(mtime) 사진만 골라낸다."""

import logging
import os
import sqlite3
from typing import Iterator

from ai_worker import config

_logger = logging.getLogger(__name__)


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


def _basename_index(paths) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for p in paths:
        index.setdefault(os.path.basename(p).lower(), []).append(p)
    return index


def repair_renamed_paths(
    conn: sqlite3.Connection,
    current: dict[str, float],
    analyzed: dict[str, float],
) -> dict[str, str]:
    """rename/move로 사라진 photos_analyzed 경로를 basename 1:1 매칭만 자동 복구.

    photos_analyzed.path/faces.photo_path를 새 경로로 UPDATE해 face_id를 그대로
    유지한다 — face_id가 바뀌면 face_labels/face_matches가 FK CASCADE로 삭제되어
    사람이 확정한 라벨이 소실되기 때문. 동명 파일 등 후보가 2개 이상(ambiguous)이면
    자동 처리하지 않고 기존처럼 orphan으로 남긴다. 반환값은 실제 반영된 {old: new}."""
    disappeared = set(analyzed) - set(current)
    new = set(current) - set(analyzed)
    if not disappeared or not new:
        return {}

    disappeared_idx = _basename_index(disappeared)
    new_idx = _basename_index(new)

    renamed: dict[str, str] = {}
    for basename, old_candidates in disappeared_idx.items():
        if len(old_candidates) != 1:
            continue
        new_candidates = new_idx.get(basename, [])
        if len(new_candidates) != 1:
            continue
        renamed[old_candidates[0]] = new_candidates[0]

    for old_path, new_path in renamed.items():
        conn.execute(
            "UPDATE photos_analyzed SET path = ?, mtime = ? WHERE path = ?",
            (new_path, current[new_path], old_path),
        )
        conn.execute(
            "UPDATE faces SET photo_path = ? WHERE photo_path = ?",
            (new_path, old_path),
        )
    if renamed:
        conn.commit()
    return renamed


def pending_photos(conn: sqlite3.Connection, root: str) -> list[tuple[str, float]]:
    """분석이 필요한 (상대 경로, mtime) 목록 — 신규 또는 mtime 변경분.

    같은 walk 결과를 재사용해 rename/move 자동 복구(repair_renamed_paths)도 함께
    수행한다(추가 walk 없음)."""
    current = dict(walk_photos(root))
    analyzed = {
        row["path"]: row["mtime"]
        for row in conn.execute("SELECT path, mtime FROM photos_analyzed")
    }

    if not current and analyzed:
        # NAS 언마운트 등으로 walk 결과가 비정상적으로 비었을 때 전체 삭제로 오인해
        # rename 로직이 대량 orphan을 만들지 않도록 이번 스캔 자체를 건너뛴다.
        _logger.warning(
            "PHOTO_ROOT에서 사진을 찾지 못했습니다(root=%s) — 접근 불가로 보고 "
            "이번 스캔을 건너뜁니다.", root,
        )
        return []

    renamed = repair_renamed_paths(conn, current, analyzed)
    for old_path, new_path in renamed.items():
        analyzed.pop(old_path, None)
        analyzed[new_path] = current[new_path]  # 재분석 대상에서 제외(rename만으로 간주)

    return [
        (rel, mtime) for rel, mtime in current.items() if analyzed.get(rel) != mtime
    ]
