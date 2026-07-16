import asyncio
import os
import aiosqlite

_DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS albums (
    id           INTEGER  PRIMARY KEY AUTOINCREMENT,
    name         TEXT     NOT NULL,
    description  TEXT,
    cover_path   TEXT,
    music_path   TEXT,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS album_photos (
    id         INTEGER  PRIMARY KEY AUTOINCREMENT,
    album_id   INTEGER  NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
    file_path  TEXT     NOT NULL,
    sort_order INTEGER  NOT NULL DEFAULT 0,
    added_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(album_id, file_path)
);

CREATE TABLE IF NOT EXISTS share_links (
    id            INTEGER  PRIMARY KEY AUTOINCREMENT,
    album_id      INTEGER  NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
    token         TEXT     NOT NULL UNIQUE,
    password_hash TEXT,
    expires_at    DATETIME,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active     BOOLEAN  NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS thumbnail_cache (
    file_path  TEXT     NOT NULL,
    size       TEXT     NOT NULL,
    thumb_path TEXT     NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (file_path, size)
);

CREATE TABLE IF NOT EXISTS photo_meta_cache (
    file_path     TEXT PRIMARY KEY,
    taken_at      TEXT,
    width         INTEGER,
    height        INTEGER,
    make          TEXT,
    camera        TEXT,
    software      TEXT,
    shutter       TEXT,
    aperture      TEXT,
    iso           INTEGER,
    focal_length  TEXT,
    shoot_mode    TEXT,
    flash         TEXT,
    metering      TEXT,
    exposure_mode TEXT,
    cache_version INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS share_link_failures (
    token        TEXT    PRIMARY KEY,
    fail_count   INTEGER NOT NULL DEFAULT 0,
    locked_until REAL    NOT NULL DEFAULT 0,
    recorded_at  REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS public_rate_limit (
    key          TEXT PRIMARY KEY,
    count        INTEGER NOT NULL DEFAULT 0,
    window_start REAL    NOT NULL
);
"""

# photo_meta_cache 캐시 버전. 이 값보다 낮은 행은 기동 시 삭제됨.
# !! 중요: photo_meta_cache 스키마 변경 또는 EXIF 추출 로직 변경 시 반드시 이 값을 올릴 것.
# 버전을 올리면 기존 캐시 전체가 삭제되고 다음 접근 시 EXIF를 새로 읽어 다시 채운다.
# v1: 전체 EXIF 컬럼(make/camera 등) 추가
# v2: 실패 읽기(width=None) 캐시 저장 금지 → 기존 빈 캐시 행 일괄 삭제
# v3: EXIF 촬영일 없으면 파일 mtime으로 taken_at 대체
_PHOTO_META_CACHE_VERSION = 3

# 기존 DB에 컬럼이 없을 때만 추가 (SQLite는 IF NOT EXISTS 미지원)
_META_CACHE_MIGRATIONS = [
    "ALTER TABLE photo_meta_cache ADD COLUMN make TEXT",
    "ALTER TABLE photo_meta_cache ADD COLUMN camera TEXT",
    "ALTER TABLE photo_meta_cache ADD COLUMN software TEXT",
    "ALTER TABLE photo_meta_cache ADD COLUMN shutter TEXT",
    "ALTER TABLE photo_meta_cache ADD COLUMN aperture TEXT",
    "ALTER TABLE photo_meta_cache ADD COLUMN iso INTEGER",
    "ALTER TABLE photo_meta_cache ADD COLUMN focal_length TEXT",
    "ALTER TABLE photo_meta_cache ADD COLUMN shoot_mode TEXT",
    "ALTER TABLE photo_meta_cache ADD COLUMN flash TEXT",
    "ALTER TABLE photo_meta_cache ADD COLUMN metering TEXT",
    "ALTER TABLE photo_meta_cache ADD COLUMN exposure_mode TEXT",
    "ALTER TABLE photo_meta_cache ADD COLUMN cache_version INTEGER NOT NULL DEFAULT 0",
]

_ALBUM_MIGRATIONS = [
    "ALTER TABLE albums ADD COLUMN slideshow_interval INTEGER",
    "ALTER TABLE albums ADD COLUMN slideshow_order    TEXT",
    "ALTER TABLE albums ADD COLUMN slideshow_effect   TEXT",
    "ALTER TABLE albums ADD COLUMN slideshow_music    INTEGER",
    "ALTER TABLE albums ADD COLUMN slideshow_volume   INTEGER",
    "ALTER TABLE albums ADD COLUMN slideshow_loop     INTEGER",
    "ALTER TABLE albums ADD COLUMN photo_sort_by      TEXT",
    "ALTER TABLE albums ADD COLUMN photo_sort_dir     TEXT",
    "ALTER TABLE albums ADD COLUMN view_count         INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE albums ADD COLUMN ui_theme           TEXT",
]


def _db_path() -> str:
    data_dir = os.getenv("DATA_DIR", "./testdata/data")
    return os.path.join(data_dir, "db", "app.db")


_DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
_pool: "asyncio.Queue[aiosqlite.Connection] | None" = None


async def _create_pooled_connection() -> aiosqlite.Connection:
    db = await aiosqlite.connect(_db_path())
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=5000")
    await db.execute("PRAGMA foreign_keys = ON")
    db.row_factory = aiosqlite.Row
    return db


async def _init_pool() -> None:
    global _pool
    if _pool is not None:
        while not _pool.empty():
            conn = _pool.get_nowait()
            await conn.close()
    _pool = asyncio.Queue()
    for _ in range(_DB_POOL_SIZE):
        await _pool.put(await _create_pooled_connection())


async def _migrate_absolute_to_relative(db) -> None:
    """album_photos.file_path의 절대 경로를 PHOTO_ROOT 기준 상대 경로로 변환."""
    photo_root = os.path.realpath(os.getenv("PHOTO_ROOT", "./testdata/photos"))
    async with db.execute("SELECT id, file_path FROM album_photos") as cur:
        rows = await cur.fetchall()
    updates = []
    for row in rows:
        row_id, path = row[0], row[1]
        if os.path.isabs(path):
            try:
                rel = os.path.relpath(path, photo_root).replace("\\", "/")
                updates.append((rel, row_id))
            except ValueError:
                pass  # Windows 다른 드라이브 간 경로: 건너뜀
    if updates:
        await db.executemany(
            "UPDATE album_photos SET file_path = ? WHERE id = ?", updates
        )


async def init_db() -> None:
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=5000")
        await db.executescript(_DDL)

        for migration in _META_CACHE_MIGRATIONS + _ALBUM_MIGRATIONS:
            try:
                await db.execute(migration)
            except aiosqlite.OperationalError:
                pass  # 이미 존재하는 컬럼이면 무시

        # cache_version이 현재 버전 미만인 행은 전체 EXIF가 없는 구 캐시 → 삭제
        await db.execute(
            "DELETE FROM photo_meta_cache WHERE cache_version < ?",
            (_PHOTO_META_CACHE_VERSION,),
        )

        await _migrate_absolute_to_relative(db)
        await db.commit()

    await _init_pool()


async def close_db_pool() -> None:
    """풀에 있는 커넥션을 모두 닫는다. 앱 종료(lifespan) 및 테스트 teardown에서 호출."""
    global _pool
    if _pool is None:
        return
    while not _pool.empty():
        conn = _pool.get_nowait()
        await conn.close()
    _pool = None


async def get_db():
    conn = await _pool.get()
    try:
        yield conn
    finally:
        await conn.rollback()  # 미커밋 트랜잭션 잔존 방지 (기존 connect-per-request의 close 동작과 동일)
        await _pool.put(conn)
