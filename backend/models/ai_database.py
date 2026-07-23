"""ai.db (Phase 2 얼굴 인식) 연결.

쓰기 주체 분리 규칙 — LumisShow는 persons·face_labels·jobs·ai_settings만 쓴다.
photos_analyzed·faces·face_matches는 AI 워커(ai_worker/) 전용 쓰기 테이블.

예외: routers/admin_people.py의 POST /api/admin/people/path-repairs/{id}/approve(-all)는
사진/폴더명 변경으로 생긴 orphan 경로를 admin이 승인한 뒤 photos_analyzed.path/faces.photo_path를
직접 UPDATE한다 — on-demand·저빈도 관리자 액션이라 WAL+busy_timeout(15s)이 워커와의
동시 쓰기를 안전하게 직렬화한다. rename 후보 자체는 ai_worker/scanner.py(야간 자동 스캔)와
POST /api/admin/people/repair-paths(수동 스캔) 양쪽이 pending_path_repairs에 제안만 쌓고,
실제 UPDATE는 admin이 승인해야만 일어난다. 같은 패턴으로 rename 후보가 전혀 없는(파일이
진짜로 사라진) 경로는 pending_orphan_cleanups에 삭제 제안으로 쌓이고,
POST /api/admin/people/orphan-cleanups/{id}/approve(-all) 승인 시에만
photos_analyzed/faces(→FK CASCADE로 face_labels/face_matches)와 photo_meta_cache(app.db)를
함께 삭제한다.

!! 스키마는 ai_worker/db.py의 _DDL과 동일하게 유지할 것 (컨테이너가 분리되어
   코드를 공유할 수 없어 복제함). 한쪽을 변경하면 반드시 다른 쪽도 변경한다.
"""

import logging
import os
import sqlite3

import aiosqlite

_logger = logging.getLogger(__name__)

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
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    type              TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending',
    requested_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    finished_at       DATETIME,
    target_person_id  INTEGER
);

CREATE TABLE IF NOT EXISTS ai_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

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
-- status는 'pending'만 쓴다 — approve/reject(dismiss) 둘 다 row를 지운다(status를
-- 'rejected'로 영구 고정하면 old_path UNIQUE 제약 때문에 다음 스캔이 재제안할 수
-- 없어 되돌리기 불가능한 상태가 됐었다).
CREATE TABLE IF NOT EXISTS pending_path_repairs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    old_path    TEXT NOT NULL UNIQUE,
    new_path    TEXT NOT NULL,
    source      TEXT NOT NULL,                     -- scan | manual
    status      TEXT NOT NULL DEFAULT 'pending',
    detected_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pending_path_repairs_status ON pending_path_repairs(status);

-- 파일이 정말로 사라진(rename 후보를 찾지 못한) 경로 — 즉시 삭제하지 않고 admin 승인 대기.
-- scanner가 INSERT만 함(source='scan'), 승인/거부는 backend가 처리(admin_people.py).
CREATE TABLE IF NOT EXISTS pending_orphan_cleanups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT NOT NULL UNIQUE,
    source      TEXT NOT NULL,                     -- scan | manual
    status      TEXT NOT NULL DEFAULT 'pending',    -- pending | rejected
    detected_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pending_orphan_cleanups_status ON pending_orphan_cleanups(status);
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
        # 별도 실행: 기존 DB에 중복된 persons.name이 있으면 인덱스 생성이
        # 실패할 수 있어 앱 부팅이 막히지 않도록 격리 (실패 시 수동 정리 필요).
        try:
            await db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_persons_name ON persons(name)"
            )
            await db.commit()
        except sqlite3.IntegrityError:
            _logger.exception(
                "persons.name UNIQUE 인덱스 생성 실패 — 중복된 이름이 있는지 확인 필요: "
                "SELECT name, COUNT(*) FROM persons GROUP BY name HAVING COUNT(*) > 1;"
            )
        # 기존 DB의 jobs 테이블에는 target_person_id 컬럼이 없을 수 있음
        # (CREATE TABLE IF NOT EXISTS는 이미 존재하는 테이블을 변경하지 않음).
        try:
            await db.execute("ALTER TABLE jobs ADD COLUMN target_person_id INTEGER")
            await db.commit()
        except sqlite3.OperationalError:
            pass  # 컬럼이 이미 존재함
        # 과거(reject를 status='rejected'로 영구 고정하던 버전)에 쌓인 row 정리 —
        # 그대로 두면 old_path UNIQUE 제약에 걸려 다음 스캔이 재제안하지 못한다.
        await db.execute("DELETE FROM pending_path_repairs WHERE status = 'rejected'")
        await db.commit()


async def get_ai_db():
    async with aiosqlite.connect(_ai_db_path()) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=15000")
        await db.execute("PRAGMA foreign_keys = ON")
        db.row_factory = aiosqlite.Row
        yield db
