"""backend/services/photo_tags.py 단위 테스트 — load_photo_tags() 일괄 조회."""

import aiosqlite

from backend.services.photo_tags import enabled_sources, load_photo_tags, search_tag_matched_paths

_ALL_SOURCES = ("ai", "manual", "person", "path", "location")


async def _seed_tags(rows: list[tuple[str, str, str]]) -> None:
    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        await db.executemany(
            "INSERT INTO photo_tags (photo_path, tag, source) VALUES (?, ?, ?)", rows
        )
        await db.commit()


async def test_load_photo_tags_groups_by_photo_and_source(client):
    await _seed_tags([
        ("2024/a.jpg", "캠핑", "ai"),
        ("2024/a.jpg", "바다", "ai"),
        ("2024/a.jpg", "서울대공원", "path"),
        ("2024/b.jpg", "서울", "location"),
    ])
    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        db.row_factory = aiosqlite.Row
        result = await load_photo_tags(
            ["2024/a.jpg", "2024/b.jpg"], db, ("ai", "path", "location")
        )

    assert sorted(result["2024/a.jpg"]["ai"]) == ["바다", "캠핑"]
    assert result["2024/a.jpg"]["path"] == ["서울대공원"]
    assert result["2024/a.jpg"]["location"] == []
    assert result["2024/b.jpg"]["location"] == ["서울"]
    assert result["2024/b.jpg"]["ai"] == []


async def test_load_photo_tags_excludes_sources_not_requested(client):
    """person 태그가 있어도 sources에 'person'을 넘기지 않으면 결과 dict 자체에
    그 키가 생기지 않는다 — 공유 링크가 person/location을 아예 조회하지 않는
    것과 동일한 안전장치(요청하지 않은 데이터는 메모리에도 안 올라옴)."""
    await _seed_tags([("2024/a.jpg", "지우", "person")])
    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        db.row_factory = aiosqlite.Row
        result = await load_photo_tags(["2024/a.jpg"], db, ("ai",))

    assert result == {"2024/a.jpg": {"ai": []}}


async def test_load_photo_tags_empty_paths_returns_empty_dict(client):
    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        db.row_factory = aiosqlite.Row
        result = await load_photo_tags([], db, ("ai", "manual"))
    assert result == {}


async def test_load_photo_tags_orders_location_city_before_country(client):
    """SQLite 기본 collation(UTF-8 바이트 순)으로는 '대한민국'이 '서울'보다 먼저 와서
    alphabetical 정렬이면 국가가 먼저 나온다 — id(삽입 순서) 정렬이라야
    geocoder.sync_location_tag()가 city를 먼저 INSERT하는 순서와 일치해
    doc/tagging_requirement.md 예시("서울, 대한민국")와 맞는다."""
    await _seed_tags([
        ("2024/a.jpg", "서울", "location"),   # city 먼저 삽입 (실제 sync_location_tag와 동일 순서)
        ("2024/a.jpg", "대한민국", "location"),  # country
    ])
    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        db.row_factory = aiosqlite.Row
        result = await load_photo_tags(["2024/a.jpg"], db, ("location",))

    assert result["2024/a.jpg"]["location"] == ["서울", "대한민국"]


async def test_load_photo_tags_empty_sources_returns_empty_lists_only(client):
    await _seed_tags([("2024/a.jpg", "캠핑", "ai")])
    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        db.row_factory = aiosqlite.Row
        result = await load_photo_tags(["2024/a.jpg"], db, ())
    assert result == {"2024/a.jpg": {}}


# ── search_tag_matched_paths ─────────────────────────────────────────────


async def test_search_tag_matched_paths_substring_match_across_sources(client):
    await _seed_tags([
        ("2024/a.jpg", "캠핑장", "ai"),
        ("2024/b.jpg", "지우", "person"),
        ("2024/c.jpg", "서울대공원", "path"),
    ])
    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        db.row_factory = aiosqlite.Row
        assert await search_tag_matched_paths("캠핑", db, _ALL_SOURCES) == {"2024/a.jpg"}
        assert await search_tag_matched_paths("지우", db, _ALL_SOURCES) == {"2024/b.jpg"}
        assert await search_tag_matched_paths("서울", db, _ALL_SOURCES) == {"2024/c.jpg"}


async def test_search_tag_matched_paths_no_match_returns_empty_set(client):
    await _seed_tags([("2024/a.jpg", "캠핑", "ai")])
    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        db.row_factory = aiosqlite.Row
        assert await search_tag_matched_paths("없는태그", db, _ALL_SOURCES) == set()


async def test_search_tag_matched_paths_deduplicates_multiple_tag_hits(client):
    """한 사진이 여러 태그로 매칭돼도(예: 'ai'와 'path' 둘 다 검색어 포함) photo_path는
    한 번만 나와야 한다(DISTINCT)."""
    await _seed_tags([
        ("2024/a.jpg", "캠핑", "ai"),
        ("2024/a.jpg", "캠핑장", "path"),
    ])
    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        db.row_factory = aiosqlite.Row
        result = await search_tag_matched_paths("캠핑", db, _ALL_SOURCES)
    assert result == {"2024/a.jpg"}


async def test_search_tag_matched_paths_escapes_like_wildcards(client):
    """검색어에 SQL LIKE 와일드카드(%, _)가 그대로 들어가도 리터럴로 취급돼야
    한다 — 이스케이프 안 하면 '_'만 검색해도 모든 태그가 걸린다."""
    await _seed_tags([("2024/a.jpg", "AXB", "ai")])
    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        db.row_factory = aiosqlite.Row
        assert await search_tag_matched_paths("_", db, _ALL_SOURCES) == set()


async def test_search_tag_matched_paths_filters_by_sources(client):
    """카테고리 off로 sources에서 제외된 source의 태그는 검색에 안 걸려야 한다."""
    await _seed_tags([
        ("2024/a.jpg", "캠핑", "ai"),
        ("2024/b.jpg", "캠핑장", "path"),
    ])
    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        db.row_factory = aiosqlite.Row
        # path 소스 제외 — a.jpg만 걸림
        assert await search_tag_matched_paths("캠핑", db, ("ai", "manual")) == {"2024/a.jpg"}


async def test_search_tag_matched_paths_empty_sources_returns_empty_set(client):
    await _seed_tags([("2024/a.jpg", "캠핑", "ai")])
    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        db.row_factory = aiosqlite.Row
        assert await search_tag_matched_paths("캠핑", db, ()) == set()


# ── enabled_sources ────────────────────────────────────────────────────────


def test_enabled_sources_all_on_returns_all_five():
    flags = {"face_enabled": True, "location_enabled": True, "path_enabled": True, "ai_tag_enabled": True}
    assert set(enabled_sources(flags)) == {"manual", "person", "location", "path", "ai"}


def test_enabled_sources_excludes_disabled_categories():
    flags = {"face_enabled": False, "location_enabled": True, "path_enabled": False, "ai_tag_enabled": True}
    assert set(enabled_sources(flags)) == {"manual", "location", "ai"}


def test_enabled_sources_manual_always_included():
    flags = {"face_enabled": False, "location_enabled": False, "path_enabled": False, "ai_tag_enabled": False}
    assert enabled_sources(flags) == ("manual",)
