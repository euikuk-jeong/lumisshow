import os
import aiosqlite

DATA_DIR = os.getenv("DATA_DIR", "./testdata/data")
DB_PATH = os.path.join(DATA_DIR, "db", "app.db")

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
"""


async def init_db() -> None:
    db_dir = os.path.dirname(DB_PATH)
    os.makedirs(db_dir, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_DDL)
        await db.commit()


async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        db.row_factory = aiosqlite.Row
        yield db
