"""backend/main.py 앱 레벨 미들웨어 단위 테스트."""


async def test_security_headers_present(client):
    r = await client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"


async def test_version_includes_default_site_title(client):
    r = await client.get("/version")
    assert r.status_code == 200
    data = r.json()
    assert "version" in data
    assert data["site_title"] == "LumisShow"


async def test_version_reflects_updated_site_title(admin_client):
    await admin_client.patch("/api/admin/settings", json={"site_title": "My Photos"})
    r = await admin_client.get("/version")
    assert r.json()["site_title"] == "My Photos"
