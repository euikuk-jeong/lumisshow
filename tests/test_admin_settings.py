
# ── GET /api/admin/settings ───────────────────────────────────────────────────

async def test_get_settings_returns_defaults(admin_client):
    r = await admin_client.get("/api/admin/settings")
    assert r.status_code == 200
    data = r.json()
    assert data["site_title"] == "LumisShow"
    assert data["timezone_offset"] == 0
    assert data["timezone_label"] == "UTC+0 (UTC)"
    assert data["slideshow_interval"] == 5
    assert data["slideshow_order"] == "sequential"
    assert data["slideshow_effect"] == "random"
    assert data["slideshow_music"] is True
    assert data["slideshow_volume"] == 25
    assert data["slideshow_loop"] is True
    assert data["browse_hidden_paths"] == []
    assert data["ui_theme"] == "dark"


async def test_get_settings_requires_auth(client):
    r = await client.get("/api/admin/settings")
    assert r.status_code == 401


# ── PATCH /api/admin/settings ─────────────────────────────────────────────────

async def test_patch_settings_updates_single_field(admin_client):
    r = await admin_client.patch("/api/admin/settings", json={"slideshow_interval": 10})
    assert r.status_code == 200
    assert r.json()["slideshow_interval"] == 10


async def test_patch_settings_preserves_other_fields(admin_client):
    await admin_client.patch("/api/admin/settings", json={"slideshow_interval": 10})
    r = await admin_client.get("/api/admin/settings")
    data = r.json()
    assert data["slideshow_interval"] == 10
    assert data["slideshow_order"] == "sequential"  # 변경 안 된 값 유지


async def test_patch_settings_updates_multiple_fields(admin_client):
    r = await admin_client.patch(
        "/api/admin/settings",
        json={"slideshow_interval": 8, "slideshow_order": "random", "ui_theme": "light"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["slideshow_interval"] == 8
    assert data["slideshow_order"] == "random"
    assert data["ui_theme"] == "light"


async def test_patch_settings_boolean_fields(admin_client):
    r = await admin_client.patch(
        "/api/admin/settings",
        json={"slideshow_music": False, "slideshow_loop": False},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["slideshow_music"] is False
    assert data["slideshow_loop"] is False


async def test_patch_settings_timezone(admin_client):
    r = await admin_client.patch(
        "/api/admin/settings",
        json={"timezone_offset": 9, "timezone_label": "UTC+9 (KST)"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["timezone_offset"] == 9
    assert data["timezone_label"] == "UTC+9 (KST)"


async def test_patch_settings_browse_hidden_paths(admin_client):
    r = await admin_client.patch(
        "/api/admin/settings",
        json={"browse_hidden_paths": ["#recycle", "@eaDir"]},
    )
    assert r.status_code == 200
    assert r.json()["browse_hidden_paths"] == ["#recycle", "@eaDir"]


async def test_patch_settings_persists_across_requests(admin_client):
    await admin_client.patch("/api/admin/settings", json={"slideshow_volume": 80})
    r = await admin_client.get("/api/admin/settings")
    assert r.json()["slideshow_volume"] == 80


async def test_patch_settings_empty_body_is_noop(admin_client):
    r = await admin_client.patch("/api/admin/settings", json={})
    assert r.status_code == 200
    assert r.json()["slideshow_interval"] == 5  # 기본값 유지


async def test_patch_settings_requires_auth(client):
    r = await client.patch("/api/admin/settings", json={"slideshow_interval": 3})
    assert r.status_code == 401


async def test_patch_settings_site_title(admin_client):
    r = await admin_client.patch("/api/admin/settings", json={"site_title": "My Photos"})
    assert r.status_code == 200
    assert r.json()["site_title"] == "My Photos"


async def test_patch_settings_site_title_rejects_empty(admin_client):
    r = await admin_client.patch("/api/admin/settings", json={"site_title": ""})
    assert r.status_code == 422


async def test_patch_settings_site_title_rejects_too_long(admin_client):
    r = await admin_client.patch("/api/admin/settings", json={"site_title": "x" * 61})
    assert r.status_code == 422
