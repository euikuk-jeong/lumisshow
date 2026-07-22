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


def detect_renamed_paths(
    current: dict[str, float],
    analyzed: dict[str, float],
) -> dict[str, str]:
    """rename/move로 사라진 photos_analyzed 경로를 basename 1:1 매칭만 탐지.

    동명 파일 등 후보가 2개 이상(ambiguous)이면 대상에서 제외한다.
    DB를 건드리지 않는 순수 함수 — 반환값은 {old: new} 매칭 후보."""
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
    return renamed


def queue_rename_proposals(
    conn: sqlite3.Connection,
    current: dict[str, float],
    analyzed: dict[str, float],
) -> dict[str, str]:
    """탐지된 rename 후보를 pending_path_repairs에 제안으로 쌓는다(즉시 UPDATE 안 함).

    실제 photos_analyzed/faces UPDATE는 admin이 승인해야 일어난다
    (backend/routers/admin_people.py의 path-repairs 승인 엔드포인트).
    old_path UNIQUE 제약이라 이미 제안된 건은 재스캔해도 중복으로 쌓이지 않는다."""
    proposed = detect_renamed_paths(current, analyzed)
    for old_path, new_path in proposed.items():
        conn.execute(
            "INSERT OR IGNORE INTO pending_path_repairs (old_path, new_path, source) "
            "VALUES (?, ?, 'scan')",
            (old_path, new_path),
        )
    if proposed:
        conn.commit()
    return proposed


def detect_orphaned_paths(
    current: dict[str, float],
    analyzed: dict[str, float],
) -> list[str]:
    """rename 후보(basename 일치)가 전혀 없는, 진짜로 사라진 photos_analyzed 경로만 추출.

    후보가 2개 이상(ambiguous)인 경우는 orphan으로 보지 않는다 — 어느 파일로
    옮겨갔는지 불확실한 상태에서 삭제 후보로 제안하면 안 되기 때문."""
    disappeared = set(analyzed) - set(current)
    if not disappeared:
        return []
    new = set(current) - set(analyzed)
    new_idx = _basename_index(new)
    return sorted(p for p in disappeared if not new_idx.get(os.path.basename(p).lower()))


def queue_orphan_proposals(
    conn: sqlite3.Connection,
    current: dict[str, float],
    analyzed: dict[str, float],
) -> list[str]:
    """탐지된 orphan 후보를 pending_orphan_cleanups에 제안으로 쌓는다(즉시 삭제 안 함).

    실제 photos_analyzed/faces 삭제는 admin이 승인해야 일어난다
    (backend/routers/admin_people.py의 orphan-cleanups 승인 엔드포인트).
    path UNIQUE 제약이라 이미 제안된 건(거부 포함)은 재스캔해도 중복으로 쌓이지 않는다."""
    orphaned = detect_orphaned_paths(current, analyzed)
    for path in orphaned:
        conn.execute(
            "INSERT OR IGNORE INTO pending_orphan_cleanups (path, source) VALUES (?, 'scan')",
            (path,),
        )
    if orphaned:
        conn.commit()
    return orphaned


def pending_photos(conn: sqlite3.Connection, root: str) -> list[tuple[str, float]]:
    """분석이 필요한 (상대 경로, mtime) 목록 — 신규 또는 mtime 변경분.

    같은 walk 결과를 재사용해 rename/move 후보 제안(queue_rename_proposals)과
    완전 삭제 후보 제안(queue_orphan_proposals)을 함께 수행한다(추가 walk 없음).
    제안된 new_path는 admin이 승인/거부하기 전까지 "신규 사진"으로 오분석되지
    않도록 분석 대상에서 제외한다."""
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

    queue_rename_proposals(conn, current, analyzed)
    queue_orphan_proposals(conn, current, analyzed)
    pending_new_paths = {
        row["new_path"]
        for row in conn.execute(
            "SELECT new_path FROM pending_path_repairs WHERE status = 'pending'"
        )
    }

    return [
        (rel, mtime) for rel, mtime in current.items()
        if analyzed.get(rel) != mtime and rel not in pending_new_paths
    ]
