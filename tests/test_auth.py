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


async def test_admin_lockout_after_max_failures(client):
    # 5 wrong attempts each return 401
    for _ in range(5):
        r = await client.post("/api/auth/login", json={"password": "wrong"})
        assert r.status_code == 401

    # 6th attempt is rate-limited
    r = await client.post("/api/auth/login", json={"password": "wrong"})
    assert r.status_code == 429

    # Correct password is also blocked during lockout
    r = await client.post("/api/auth/login", json={"password": "testpass"})
    assert r.status_code == 429


async def test_login_with_bcrypt_hash_password(tmp_path, monkeypatch):
    """ADMIN_PASSWORD_HASH(bcrypt) 환경변수로 로그인이 동작한다."""
    import bcrypt
    from httpx import ASGITransport, AsyncClient

    pw_hash = bcrypt.hashpw(b"hashpass", bcrypt.gensalt()).decode()
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PHOTO_ROOT", str(tmp_path / "photos"))
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", pw_hash)
    monkeypatch.setenv("JWT_SECRET", "testsecret")
    (tmp_path / "photos").mkdir(parents=True, exist_ok=True)

    from backend.models.database import init_db
    await init_db()
    from backend.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"password": "hashpass"})
        assert r.status_code == 200

        r = await c.post("/api/auth/login", json={"password": "wronghash"})
        assert r.status_code == 401


async def test_me_with_share_session_token_fails(admin_client):
    """공유 세션 토큰을 Admin Bearer로 사용하면 401 반환."""
    from backend.services.auth import create_share_session_token
    share_jwt = create_share_session_token("some-share-token")
    r = await admin_client.get("/api/auth/me", headers={"Authorization": f"Bearer {share_jwt}"})
    assert r.status_code == 401


async def test_admin_lockout_clears_on_success(client):
    # 4 wrong attempts
    for _ in range(4):
        await client.post("/api/auth/login", json={"password": "wrong"})

    # Success clears the failure counter
    r = await client.post("/api/auth/login", json={"password": "testpass"})
    assert r.status_code == 200

    # 4 more wrong attempts should not trigger lockout (counter was reset)
    for _ in range(4):
        r = await client.post("/api/auth/login", json={"password": "wrong"})
    assert r.status_code == 401  # still 401, not 429
