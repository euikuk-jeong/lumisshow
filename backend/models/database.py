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
    file_path TEXT PRIMARY KEY,
    taken_at  TEXT,
    width     INTEGER,
    height    INTEGER
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# 기존 DB에 컬럼이 없을 때만 추가 (SQLite는 IF NOT EXISTS 미지원)
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
]


def _db_path() -> str:
    data_dir = os.getenv("DATA_DIR", "./testdata/data")
    return os.path.join(data_dir, "db", "app.db")


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
        await db.executescript(_DDL)
        for migration in _ALBUM_MIGRATIONS:
            try:
                await db.execute(migration)
            except aiosqlite.OperationalError:
                pass  # 이미 존재하는 컬럼이면 무시
        await _migrate_absolute_to_relative(db)
        await db.commit()


async def get_db():
    async with aiosqlite.connect(_db_path()) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        db.row_factory = aiosqlite.Row
        yield db
