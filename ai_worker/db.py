"""ai.db 연결/스키마. 워커는 photos_analyzed·faces·face_matches를 쓰고
persons·face_labels·jobs·ai_settings는 LumisShow가 쓴다 (jobs.status만 워커가 갱신)."""

import logging
import os
import sqlite3

from ai_worker import config

_logger = logging.getLogger(__name__)

_DDL = """
PRAGMA foreign_keys = ON;

-- ── 워커가 쓰는 테이블 ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS photos_analyzed (
    path        TEXT PRIMARY KEY,              -- PHOTO_ROOT 상대 경로 (/ 구분자)
    mtime       REAL NOT NULL,
    analyzed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    face_count  INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'done'   -- done | error
);

CREATE TABLE IF NOT EXISTS faces (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_path TEXT NOT NULL,
    bbox       TEXT NOT NULL,                  -- JSON [x1, y1, x2, y2]
    det_score  REAL NOT NULL,
    embedding  BLOB NOT NULL                   -- float32 512차원
);
CREATE INDEX IF NOT EXISTS idx_faces_photo ON faces(photo_path);

CREATE TABLE IF NOT EXISTS face_matches (
    face_id    INTEGER PRIMARY KEY REFERENCES faces(id) ON DELETE CASCADE,
    person_id  INTEGER NOT NULL,
    score      REAL NOT NULL,
    matched_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_face_matches_person ON face_matches(person_id);

-- ── LumisShow가 쓰는 테이블 ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS persons (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS face_labels (
    face_id    INTEGER PRIMARY KEY REFERENCES faces(id) ON DELETE CASCADE,
    person_id  INTEGER,                        -- NULL = 무시(등록 인물 아님)
    labeled_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_face_labels_person ON face_labels(person_id);

CREATE TABLE IF NOT EXISTS jobs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    type              TEXT NOT NULL,                -- scan | rematch | review_ignored
    status            TEXT NOT NULL DEFAULT 'pending',  -- pending | running | done | error
    requested_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    finished_at       DATETIME,
    target_person_id  INTEGER                    -- review_ignored 전용: 대상 인물
);

CREATE TABLE IF NOT EXISTS ai_settings (
    key   TEXT PRIMARY KEY,                    -- 예: scan_hour
    value TEXT NOT NULL
);

-- '무시' 라벨 얼굴을 특정 인물 1명 기준으로 재검토한 결과 후보
-- (워커가 씀: review_ignored 잡 처리 시 DELETE+INSERT로 해당 인물 몫만 교체)
CREATE TABLE IF NOT EXISTS ignored_review_candidates (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    face_id    INTEGER NOT NULL REFERENCES faces(id) ON DELETE CASCADE,
    person_id  INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    score      REAL NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ignored_review_person ON ignored_review_candidates(person_id);

-- rename/move 자동 감지 후보(basename 1:1 매칭) — 즉시 적용하지 않고 admin 승인 대기.
-- scanner가 INSERT만 함(source='scan'), 승인/거부는 backend가 처리(admin_people.py).
CREATE TABLE IF NOT EXISTS pending_path_repairs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    old_path    TEXT NOT NULL UNIQUE,
    new_path    TEXT NOT NULL,
    source      TEXT NOT NULL,                     -- scan | manual
    status      TEXT NOT NULL DEFAULT 'pending',    -- pending | rejected
    detected_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pending_path_repairs_status ON pending_path_repairs(status);
"""


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or config.ai_db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    # 별도 실행: 기존 DB에 중복된 persons.name이 있으면 인덱스 생성이
    # 실패할 수 있어 워커 부팅이 막히지 않도록 격리 (실패 시 수동 정리 필요).
    try:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_persons_name ON persons(name)")
    except sqlite3.IntegrityError:
        _logger.exception(
            "persons.name UNIQUE 인덱스 생성 실패 — 중복된 이름이 있는지 확인 필요: "
            "SELECT name, COUNT(*) FROM persons GROUP BY name HAVING COUNT(*) > 1;"
        )
    # 기존 DB의 jobs 테이블에는 target_person_id 컬럼이 없을 수 있음
    # (CREATE TABLE IF NOT EXISTS는 이미 존재하는 테이블을 변경하지 않음).
    try:
        conn.execute("ALTER TABLE jobs ADD COLUMN target_person_id INTEGER")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # 컬럼이 이미 존재함
    return conn
