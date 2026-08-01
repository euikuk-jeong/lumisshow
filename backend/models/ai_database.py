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

-- cover_face_id: admin이 명시적으로 지정한 커버 얼굴(face_labels.face_id). NULL이면
-- 자동(가장 먼저 확정된 얼굴)으로 표시한다. FK를 걸지 않는다 — face_labels.person_id와
-- 같은 이유로, 얼굴이 삭제/재라벨돼도 조회 시점에 유효성만 확인하고 자동 폴백한다.
CREATE TABLE IF NOT EXISTS persons (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    cover_face_id  INTEGER
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

-- 사물/장면/위치/폴더명/인물 태그. 워커(ai/path/location)와 LumisShow(manual/person)
-- 양쪽이 상시 쓰는 첫 ai.db 테이블 — WAL+busy_timeout으로 동시 쓰기를 직렬화한다.
-- source가 다르면 같은 텍스트가 동시에 존재할 수 있어(예: GPS location='서울' +
-- 폴더명 path='서울') UNIQUE에 source를 포함한다.
CREATE TABLE IF NOT EXISTS photo_tags (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_path TEXT NOT NULL,
    tag        TEXT NOT NULL,
    source     TEXT NOT NULL DEFAULT 'manual',  -- ai | manual | person | path | location
    person_id  INTEGER,                 -- source='person'일 때만 값 존재 (FK 없음, face_labels 관례와 동일)
    confidence REAL,
    tagged_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (photo_path, tag, source)
);
CREATE INDEX IF NOT EXISTS idx_photo_tags_tag ON photo_tags(tag);
CREATE INDEX IF NOT EXISTS idx_photo_tags_person ON photo_tags(person_id);

-- GPS EXIF 역지오코딩 결과(정본). photo_tags(source='location')는 이 값의 복제본 —
-- city/country가 바뀌거나 사라지면 geocoder.sync_location_tag()(ai_worker)가 함께 정리한다.
CREATE TABLE IF NOT EXISTS photo_locations (
    photo_path TEXT PRIMARY KEY,
    city       TEXT,
    country    TEXT,
    source     TEXT NOT NULL DEFAULT 'exif_gps',  -- exif_gps | manual
    tagged_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- CLIP 이미지 임베딩 캐시(float32 512차원). 태그 어휘(ai_worker/tag_vocab.py)나
-- threshold가 바뀌어도 이미지 재인코딩 없이 저장된 벡터로 재채점하기 위함
-- (Phase 4 tag-backfill).
CREATE TABLE IF NOT EXISTS photo_embeddings (
    photo_path TEXT PRIMARY KEY,
    embedding  BLOB NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
        # 기존 DB의 persons 테이블에는 cover_face_id 컬럼이 없을 수 있음
        try:
            await db.execute("ALTER TABLE persons ADD COLUMN cover_face_id INTEGER")
            await db.commit()
        except sqlite3.OperationalError:
            pass  # 컬럼이 이미 존재함
        # 과거(reject를 status='rejected'로 영구 고정하던 버전)에 쌓인 row 정리 —
        # 그대로 두면 old_path UNIQUE 제약에 걸려 다음 스캔이 재제안하지 못한다.
        await db.execute("DELETE FROM pending_path_repairs WHERE status = 'rejected'")
        # photo_tags(source='person') 소급: 이 컬럼이 추가되기 전부터 있던 face_labels는
        # 이벤트 기반 동기화(admin_people.py)를 한 번도 안 거쳤으므로 태그가 비어있다.
        # ON CONFLICT DO NOTHING이라 매 시작마다 실행해도 안전(idempotent)하며,
        # 이후 라벨 변경은 admin_people.py의 _sync_person_tag가 실시간으로 반영한다.
        await db.execute(
            """INSERT INTO photo_tags (photo_path, tag, source, person_id)
               SELECT DISTINCT f.photo_path, p.name, 'person', p.id
               FROM face_labels fl
               JOIN faces f ON f.id = fl.face_id
               JOIN persons p ON p.id = fl.person_id
               WHERE fl.person_id IS NOT NULL
               ON CONFLICT(photo_path, tag, source) DO NOTHING"""
        )
        # 반대 방향 정리: 워커가 mtime 변경으로 사진을 재분석하면 faces를 DELETE(FK
        # CASCADE로 face_labels도 함께 삭제)하지만 photo_tags는 워커가 건드리지
        # 않으므로 이벤트 동기화(_sync_person_tag)가 발동하지 않는다. 그대로 두면
        # 라벨이 사라진 뒤에도 person 태그가 유령처럼 남는다 — _sync_person_tag가
        # 지키는 불변식(라벨이 실제로 없으면 태그도 없다)의 역방향을 여기서 보정한다.
        await db.execute(
            """DELETE FROM photo_tags
               WHERE source = 'person'
                 AND NOT EXISTS (
                   SELECT 1 FROM faces f
                   JOIN face_labels fl ON fl.face_id = f.id
                   WHERE f.photo_path = photo_tags.photo_path
                     AND fl.person_id = photo_tags.person_id
                 )"""
        )
        await db.commit()


async def get_ai_db():
    async with aiosqlite.connect(_ai_db_path()) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=15000")
        await db.execute("PRAGMA foreign_keys = ON")
        db.row_factory = aiosqlite.Row
        yield db
