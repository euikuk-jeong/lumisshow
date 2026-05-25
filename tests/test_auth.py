async def test_login_success(client):
    r = await client.post("/api/auth/login", json={"password": "testpass"})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


async def test_login_wrong_password(client):
    r = await client.post("/api/auth/login", json={"password": "wrong"})
    assert r.status_code == 401


async def test_me_with_valid_token(admin_client):
    r = await admin_client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["user"] == "admin"


async def test_me_without_token(client):
    r = await client.get("/api/auth/me")
    assert r.status_code == 401  # HTTPBearer: credentials not provided


async def test_me_with_invalid_token(client):
    r = await client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
    assert r.status_code == 401


async def test_logout(admin_client):
    r = await admin_client.post("/api/auth/logout")
    assert r.status_code == 200
