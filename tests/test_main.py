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


async def test_assets_served_with_no_cache(client):
    # 버전 쿼리 없이 서빙되므로 배포 후 옛 JS가 heuristic 캐시로 남지 않게 매번 재검증
    r = await client.get("/assets/js/pages/admin-albums.js")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-cache"
    assert "etag" in r.headers


async def test_assets_revalidation_returns_304(client):
    r = await client.get("/assets/js/pages/admin-albums.js")
    r2 = await client.get("/assets/js/pages/admin-albums.js", headers={"If-None-Match": r.headers["etag"]})
    assert r2.status_code == 304
    assert r2.headers["cache-control"] == "no-cache"


async def test_spa_html_served_with_no_cache(client):
    for path in ("/", "/admin/albums", "/s/nonexistent"):
        r = await client.get(path)
        assert r.status_code == 200
        assert r.headers["cache-control"] == "no-cache", path


async def test_api_json_has_no_forced_cache_control(client):
    r = await client.get("/health")
    assert "cache-control" not in r.headers
