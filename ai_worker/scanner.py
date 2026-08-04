"""PHOTO_ROOT 증분 스캔 — 미분석/변경(mtime) 사진만 골라낸다."""

import logging
import os
import sqlite3
from typing import Iterator

from ai_worker import config

_logger = logging.getLogger(__name__)

# Kiwi가 뽑은 1음절 명사(예: "캠핑장"→"캠핑"+"장")는 조사성 접미 파편일 가능성이 높아
# 태그로서 의미가 거의 없고, "-장"/"-실" 같은 흔한 접미어가 여러 폴더에서 반복돼
# 노이즈가 되므로 제외한다.
_MIN_NOUN_LEN = 2
_kiwi = None

# status='error' 사진 재시도 주기 — 너무 짧으면 지속 실패 파일 때문에 매 스캔
# pending이 비지 않아 모델 로딩 비용·Discord 알림이 매번 발생하고, 너무 길면
# 일시적 오류로 실패한 사진이 오래 방치된다.
_ERROR_RETRY_DAYS = 7


def _get_kiwi():
    """Kiwi()는 사전 로딩 비용이 있어(수백ms~1초대) 모듈 전역에 1회만 만들어
    재사용한다. insightface와 동일하게 무거운 의존성이라 lazy import —
    scanner 단위 테스트는 kiwipiepy 설치 없이도 다른 함수는 그대로 실행 가능."""
    global _kiwi
    if _kiwi is None:
        from kiwipiepy import Kiwi

        _kiwi = Kiwi()
    return _kiwi


def extract_folder_nouns(folder_name: str) -> list[str]:
    """폴더명에서 명사(NNG/NNP)만 순서·중복 제거해 추출한다."""
    tokens = _get_kiwi().tokenize(folder_name)
    nouns: list[str] = []
    for t in tokens:
        if t.tag in ("NNG", "NNP") and len(t.form) >= _MIN_NOUN_LEN and t.form not in nouns:
            nouns.append(t.form)
    return nouns


def tag_paths_from_folder_names(conn: sqlite3.Connection) -> int:
    """photos_analyzed 중 아직 폴더명 태깅을 시도하지 않은(`path_tag_done = 0`) 사진의
    바로 상위 폴더명을 Kiwi로 분석해 photo_tags(source='path')에 기록한다.

    mtime 기반 pending_photos()와 무관하게 "커버리지"로 동작한다 — `path_tag_done`
    플래그가 0인 사진만 대상으로 삼기 때문에, 이 기능 도입 이전 사진(기존 4.5만 장)도
    다음 스캔에서 자연히 채워지고, 경로복구 승인(admin_people.py의 _apply_path_repair가
    rename 시 photo_tags(source='path')를 지우면서 path_tag_done도 0으로 되돌림 — Kiwi는
    워커 전용이라 백엔드에서 재계산할 수 없음) 이후에도 다음 스캔이 이어서 채운다.
    같은 폴더는 1회만 Kiwi를 실행해 재사용한다(폴더 단위 캐싱).

    명사가 하나도 없는 폴더(예: 순수 영문/숫자 폴더명)의 사진은 태그가 안 생기지만
    `path_tag_done`은 시도 여부만 보고 1로 표시하므로 다음 스캔부터 재시도하지 않는다
    (한때는 photo_tags 행 존재 여부로 커버리지를 판단해 이런 사진이 매 스캔 재시도되며
    알림 로그의 path_tagged 건수를 실제 신규 작업 없이 계속 부풀렸었다 — 2026-08-04
    사용자 피드백으로 photos_analyzed.path_tag_done 플래그 기반으로 전환)."""
    rows = conn.execute(
        "SELECT path FROM photos_analyzed WHERE path_tag_done = 0"
    ).fetchall()
    if not rows:
        return 0

    folder_cache: dict[str, list[str]] = {}
    tagged = 0
    for row in rows:
        path = row["path"]
        folder = os.path.basename(os.path.dirname(path))
        if folder not in folder_cache:
            folder_cache[folder] = extract_folder_nouns(folder) if folder else []
        nouns = folder_cache[folder]
        for noun in nouns:
            conn.execute(
                """INSERT INTO photo_tags (photo_path, tag, source) VALUES (?, ?, 'path')
                   ON CONFLICT(photo_path, tag, source) DO NOTHING""",
                (path, noun),
            )
        if nouns:
            tagged += 1
        conn.execute(
            "UPDATE photos_analyzed SET path_tag_done = 1 WHERE path = ?", (path,)
        )
    conn.commit()
    return tagged


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
    """분석이 필요한 (상대 경로, mtime) 목록 — 신규, mtime 변경분, 또는
    `_ERROR_RETRY_DAYS`일 넘게 지난 status='error' 사진(파일이 안 바뀌어 mtime이
    그대로여도 주기적으로 재시도) — 매 스캔 무조건 재시도하면 지속적으로 실패하는
    파일(손상 등) 때문에 매일 밤 pending이 절대 비지 않아 모델 로딩 비용을 매번
    치르고 Discord 알림도 매번 발송돼버린다(둘 다 "증분 없으면 스킵" 원칙 위반).

    같은 walk 결과를 재사용해 rename/move 후보 제안(queue_rename_proposals)과
    완전 삭제 후보 제안(queue_orphan_proposals)을 함께 수행한다(추가 walk 없음).
    제안된 new_path는 admin이 승인/거부하기 전까지 "신규 사진"으로 오분석되지
    않도록 분석 대상에서 제외한다."""
    current = dict(walk_photos(root))
    analyzed_rows = conn.execute("SELECT path, mtime FROM photos_analyzed").fetchall()
    analyzed = {row["path"]: row["mtime"] for row in analyzed_rows}
    error_paths = {
        row["path"] for row in conn.execute(
            "SELECT path FROM photos_analyzed WHERE status = 'error' "
            "AND (analyzed_at IS NULL OR analyzed_at < datetime('now', ?))",
            (f"-{_ERROR_RETRY_DAYS} days",),
        )
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
        if (analyzed.get(rel) != mtime or rel in error_paths) and rel not in pending_new_paths
    ]
