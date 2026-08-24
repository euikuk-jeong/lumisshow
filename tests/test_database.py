"""backend/models/database.py 커넥션 풀(get_db) 단위 테스트."""

import asyncio

import pytest_asyncio

from backend.models.database import close_db_pool, get_db, init_db


@pytest_asyncio.fixture
async def db_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PHOTO_ROOT", str(tmp_path / "photos"))
    (tmp_path / "photos").mkdir(parents=True, exist_ok=True)
    await init_db()
    yield
    await close_db_pool()


async def test_get_db_reused_across_sequential_calls(db_env):
    for _ in range(10):
        gen = get_db()
        db = await gen.__anext__()
        async with db.execute("SELECT 1 AS n") as cur:
            row = await cur.fetchone()
        assert row["n"] == 1
        await gen.aclose()


async def test_get_db_supports_more_concurrent_users_than_pool_size(db_env):
    async def borrow():
        gen = get_db()
        db = await gen.__anext__()
        await asyncio.sleep(0.01)
        async with db.execute("SELECT 1 AS n") as cur:
            row = await cur.fetchone()
        await gen.aclose()
        return row["n"]

    results = await asyncio.gather(*(borrow() for _ in range(20)))
    assert results == [1] * 20


async def test_close_db_pool_is_idempotent(db_env):
    await close_db_pool()
    await close_db_pool()  # 재호출해도 예외 없이 안전


async def test_migrate_legacy_title_font_nanum_pen_to_gaegu(db_env):
    """손글씨체 대표 폰트 nanum-pen → gaegu 교체에 따른 기존 앨범 값 마이그레이션."""
    gen = get_db()
    db = await gen.__anext__()
    await db.execute(
        "INSERT INTO albums (name, title_font) VALUES (?, ?)", ("Legacy", "nanum-pen")
    )
    await db.commit()
    await gen.aclose()

    await init_db()  # 재기동 시뮬레이션 — 마이그레이션 재실행

    gen2 = get_db()
    db2 = await gen2.__anext__()
    async with db2.execute(
        "SELECT title_font FROM albums WHERE name = ?", ("Legacy",)
    ) as cur:
        row = await cur.fetchone()
    assert row["title_font"] == "gaegu"
    await gen2.aclose()


async def test_get_db_rolls_back_uncommitted_write_on_exit(db_env):
    """커밋 전 예외 발생 시 미완료 트랜잭션이 다음 요청으로 전파되면 안 된다."""
    gen = get_db()
    db = await gen.__anext__()
    await db.execute(
        "INSERT INTO albums (name) VALUES (?)", ("uncommitted",)
    )
    # commit() 호출 없이 종료 — rollback 없이 반환하면 다음 borrower가 이 미커밋 write를 물려받음
    await gen.aclose()

    gen2 = get_db()
    db2 = await gen2.__anext__()
    async with db2.execute("SELECT COUNT(*) AS n FROM albums WHERE name = ?", ("uncommitted",)) as cur:
        row = await cur.fetchone()
    assert row["n"] == 0
    await gen2.aclose()
