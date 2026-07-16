"""ai.db (Phase 2 얼굴 인식) 연결.

쓰기 주체 분리 규칙 — LumisShow는 persons·face_labels·jobs·ai_settings만 쓴다.
photos_analyzed·faces·face_matches는 AI 워커(ai_worker/) 전용 쓰기 테이블.

!! 스키마는 ai_worker/db.py의 _DDL과 동일하게 유지할 것 (컨테이너가 분리되어
   코드를 공유할 수 없어 복제함). 한쪽을 변경하면 반드시 다른 쪽도 변경한다.
"""

import os

import aiosqlite

_AI_DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS photos_analyzed (
    path        TEXT PRIMARY KEY,
    mtime       REAL NOT NULL,
    analyzed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    face_count  INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'done'
);

CREATE TABLE IF NOT EXISTS faces (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_path TEXT NOT NULL,
    bbox       TEXT NOT NULL,
    det_score  REAL NOT NULL,
    embedding  BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_faces_photo ON faces(photo_path);

CREATE TABLE IF NOT EXISTS face_matches (
    face_id    INTEGER PRIMARY KEY REFERENCES faces(id) ON DELETE CASCADE,
    person_id  INTEGER NOT NULL,
    score      REAL NOT NULL,
    matched_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_face_matches_person ON face_matches(person_id);

CREATE TABLE IF NOT EXISTS persons (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS face_labels (
    face_id    INTEGER PRIMARY KEY REFERENCES faces(id) ON DELETE CASCADE,
    person_id  INTEGER,
    labeled_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_face_labels_person ON face_labels(person_id);

CREATE TABLE IF NOT EXISTS jobs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    type         TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    finished_at  DATETIME
);

CREATE TABLE IF NOT EXISTS ai_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _ai_db_path() -> str:
    data_dir = os.getenv("DATA_DIR", "./testdata/data")
    return os.path.join(data_dir, "db", "ai.db")


def faces_dir() -> str:
    return os.path.join(os.getenv("DATA_DIR", "./testdata/data"), "faces")


async def init_ai_db() -> None:
    path = _ai_db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=15000")
        await db.executescript(_AI_DDL)
        await db.commit()


async def get_ai_db():
    async with aiosqlite.connect(_ai_db_path()) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=15000")
        await db.execute("PRAGMA foreign_keys = ON")
        db.row_factory = aiosqlite.Row
        yield db
