"""admin_ai_tags 라우터 테스트 — ai.db photo_tags 기반 Admin 태그 관리 API."""

import aiosqlite


async def _insert_tags(rows: list[tuple[str, str, str]]) -> None:
    """(photo_path, tag, source) 튜플 목록을 photo_tags에 직접 삽입 (워커/기존 동작 대행)."""
    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        await db.executemany(
            "INSERT INTO photo_tags (photo_path, tag, source) VALUES (?, ?, ?)", rows
        )
        await db.commit()


async def _tag_rows(tag: str | None = None, source: str | None = None) -> list[dict]:
    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        db.row_factory = aiosqlite.Row
        sql = "SELECT photo_path, tag, source FROM photo_tags WHERE 1=1"
        params: list = []
        if tag is not None:
            sql += " AND tag = ?"
            params.append(tag)
        if source is not None:
            sql += " AND source = ?"
            params.append(source)
        async with db.execute(sql, params) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ── GET /tags ────────────────────────────────────────────────────────────


async def test_list_tags_groups_by_tag_and_source_with_counts(admin_client):
    await _insert_tags([
        ("2024/a.jpg", "캠핑", "ai"),
        ("2024/b.jpg", "캠핑", "ai"),
        ("2024/c.jpg", "캠핑", "path"),
        ("2024/d.jpg", "서울", "location"),
    ])
    r = await admin_client.get("/api/admin/tags")
    assert r.status_code == 200
    tags = {(t["tag"], t["source"]): t["count"] for t in r.json()["tags"]}
    assert tags[("캠핑", "ai")] == 2
    assert tags[("캠핑", "path")] == 1
    assert tags[("서울", "location")] == 1


async def test_list_tags_excludes_person_source(admin_client):
    await _insert_tags([("2024/a.jpg", "지우", "person")])
    r = await admin_client.get("/api/admin/tags")
    assert r.json()["tags"] == []


async def test_list_tags_includes_sample_path(admin_client):
    await _insert_tags([("2024/a.jpg", "캠핑", "ai")])
    r = await admin_client.get("/api/admin/tags")
    tags = r.json()["tags"]
    assert tags[0]["sample_path"] == "2024/a.jpg"


async def test_list_tags_requires_auth(client):
    r = await client.get("/api/admin/tags")
    assert r.status_code in (401, 403)


# ── GET /tags/vocab ──────────────────────────────────────────────────────


async def test_get_manual_tag_vocab_returns_list(admin_client):
    r = await admin_client.get("/api/admin/tags/vocab")
    assert r.status_code == 200
    vocab = r.json()["vocab"]
    assert "캠핑" in vocab
    assert len(vocab) == 80


# ── GET /tags/{tag}/photos ───────────────────────────────────────────────


async def test_list_tag_photos_returns_photos_for_source(admin_client):
    await _insert_tags([
        ("2024/a.jpg", "캠핑", "ai"),
        ("2024/b.jpg", "캠핑", "ai"),
        ("2024/c.jpg", "캠핑", "path"),
    ])
    r = await admin_client.get("/api/admin/tags/캠핑/photos?source=ai")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert {p["file_path"] for p in body["photos"]} == {"2024/a.jpg", "2024/b.jpg"}


async def test_list_tag_photos_returns_photos_for_location_source(admin_client):
    """location은 rename/delete는 거부하지만(편집 불가) 조회는 다른 source와 동일하게
    허용돼야 한다 — 이 라우터의 '조회 가능·편집 불가' 구분의 절반(조회)을 검증."""
    await _insert_tags([("2024/a.jpg", "서울", "location")])
    r = await admin_client.get("/api/admin/tags/서울/photos?source=location")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["photos"][0]["file_path"] == "2024/a.jpg"


async def test_list_tag_photos_empty_when_no_match(admin_client):
    r = await admin_client.get("/api/admin/tags/없는태그/photos?source=ai")
    assert r.status_code == 200
    assert r.json() == {"photos": [], "total": 0, "page": 1, "snapshot": None}


async def test_list_tag_photos_rejects_invalid_source(admin_client):
    r = await admin_client.get("/api/admin/tags/캠핑/photos?source=person")
    assert r.status_code == 400


async def test_list_tag_photos_requires_auth(client):
    r = await client.get("/api/admin/tags/캠핑/photos?source=ai")
    assert r.status_code in (401, 403)


# ── DELETE /tags/{tag}/photo ─────────────────────────────────────────────


async def test_delete_tag_from_photo_removes_row(admin_client):
    await _insert_tags([("2024/a.jpg", "캠핑", "ai"), ("2024/a.jpg", "바다", "ai")])
    r = await admin_client.delete("/api/admin/tags/캠핑/photo?path=2024/a.jpg&source=ai")
    assert r.status_code == 204
    remaining = await _tag_rows(source="ai")
    assert remaining == [{"photo_path": "2024/a.jpg", "tag": "바다", "source": "ai"}]


async def test_delete_tag_from_photo_404_when_not_found(admin_client):
    r = await admin_client.delete("/api/admin/tags/없음/photo?path=2024/a.jpg&source=ai")
    assert r.status_code == 404


async def test_delete_tag_from_photo_rejects_location_source(admin_client):
    await _insert_tags([("2024/a.jpg", "서울", "location")])
    r = await admin_client.delete("/api/admin/tags/서울/photo?path=2024/a.jpg&source=location")
    assert r.status_code == 400
    assert await _tag_rows(source="location") == [
        {"photo_path": "2024/a.jpg", "tag": "서울", "source": "location"}
    ]


async def test_delete_tag_from_photo_rejects_person_source(admin_client):
    await _insert_tags([("2024/a.jpg", "지우", "person")])
    r = await admin_client.delete("/api/admin/tags/지우/photo?path=2024/a.jpg&source=person")
    assert r.status_code == 400


async def test_delete_tag_from_photo_requires_auth(client):
    r = await client.delete("/api/admin/tags/캠핑/photo?path=2024/a.jpg&source=ai")
    assert r.status_code in (401, 403)


# ── PUT /tags/{tag}/rename ────────────────────────────────────────────────


async def test_rename_tag_updates_all_rows_for_source(admin_client):
    await _insert_tags([
        ("2024/a.jpg", "캠핑", "ai"),
        ("2024/b.jpg", "캠핑", "ai"),
        ("2024/c.jpg", "캠핑", "path"),  # 다른 source — 영향받지 않아야 함
    ])
    r = await admin_client.put("/api/admin/tags/캠핑/rename", json={"new_tag": "야영", "source": "ai"})
    assert r.status_code == 200
    assert r.json() == {"tag": "야영", "source": "ai", "count": 2}
    assert {row["photo_path"] for row in await _tag_rows(tag="야영", source="ai")} == {
        "2024/a.jpg", "2024/b.jpg"
    }
    assert await _tag_rows(tag="캠핑", source="path") == [
        {"photo_path": "2024/c.jpg", "tag": "캠핑", "source": "path"}
    ]


async def test_rename_tag_merges_duplicate_on_conflict(admin_client):
    """new_tag가 같은 사진·source에 이미 존재하면(UNIQUE 충돌) 옛 행만 지우고
    중복을 남기지 않아야 한다."""
    await _insert_tags([
        ("2024/a.jpg", "캠핑", "ai"),
        ("2024/a.jpg", "야영", "ai"),  # 이미 존재 — rename 시 충돌
    ])
    r = await admin_client.put("/api/admin/tags/캠핑/rename", json={"new_tag": "야영", "source": "ai"})
    assert r.status_code == 200
    rows = await _tag_rows(source="ai")
    assert rows == [{"photo_path": "2024/a.jpg", "tag": "야영", "source": "ai"}]


async def test_rename_tag_404_when_not_found(admin_client):
    r = await admin_client.put("/api/admin/tags/없음/rename", json={"new_tag": "새태그", "source": "ai"})
    assert r.status_code == 404


async def test_rename_tag_rejects_location_source(admin_client):
    await _insert_tags([("2024/a.jpg", "서울", "location")])
    r = await admin_client.put(
        "/api/admin/tags/서울/rename", json={"new_tag": "서울시", "source": "location"}
    )
    assert r.status_code == 400


async def test_rename_tag_rejects_blank_new_tag(admin_client):
    await _insert_tags([("2024/a.jpg", "캠핑", "ai")])
    r = await admin_client.put("/api/admin/tags/캠핑/rename", json={"new_tag": "   ", "source": "ai"})
    assert r.status_code == 400


async def test_rename_tag_requires_auth(client):
    r = await client.put("/api/admin/tags/캠핑/rename", json={"new_tag": "야영", "source": "ai"})
    assert r.status_code in (401, 403)


# ── POST /tags/manual ────────────────────────────────────────────────────


async def test_add_manual_tag_inserts_row(admin_client):
    r = await admin_client.post(
        "/api/admin/tags/manual", json={"photo_path": "2024/a.jpg", "tag": "캠핑"}
    )
    assert r.status_code == 201
    assert r.json() == {"photo_path": "2024/a.jpg", "tag": "캠핑", "source": "manual", "added": True}
    assert await _tag_rows(tag="캠핑", source="manual") == [
        {"photo_path": "2024/a.jpg", "tag": "캠핑", "source": "manual"}
    ]


async def test_add_manual_tag_rejects_non_vocab_tag(admin_client):
    r = await admin_client.post(
        "/api/admin/tags/manual", json={"photo_path": "2024/a.jpg", "tag": "존재하지않는태그"}
    )
    assert r.status_code == 400
    assert await _tag_rows() == []


async def test_add_manual_tag_idempotent_returns_added_false_on_duplicate(admin_client):
    await admin_client.post("/api/admin/tags/manual", json={"photo_path": "2024/a.jpg", "tag": "캠핑"})
    r = await admin_client.post(
        "/api/admin/tags/manual", json={"photo_path": "2024/a.jpg", "tag": "캠핑"}
    )
    assert r.status_code == 201
    assert r.json()["added"] is False
    assert len(await _tag_rows(tag="캠핑", source="manual")) == 1


async def test_add_manual_tag_requires_auth(client):
    r = await client.post("/api/admin/tags/manual", json={"photo_path": "2024/a.jpg", "tag": "캠핑"})
    assert r.status_code in (401, 403)
