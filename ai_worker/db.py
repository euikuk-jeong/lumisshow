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
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    type         TEXT NOT NULL,                -- scan | rematch
    status       TEXT NOT NULL DEFAULT 'pending',  -- pending | running | done | error
    requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    finished_at  DATETIME
);

CREATE TABLE IF NOT EXISTS ai_settings (
    key   TEXT PRIMARY KEY,                    -- 예: scan_hour
    value TEXT NOT NULL
);
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
    return conn
