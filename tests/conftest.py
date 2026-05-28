import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PHOTO_ROOT", str(tmp_path / "photos"))
    monkeypatch.setenv("ADMIN_PASSWORD", "testpass")
    monkeypatch.setenv("JWT_SECRET", "testsecret")
    (tmp_path / "photos").mkdir(parents=True, exist_ok=True)

    from backend.models.database import init_db
    await init_db()

    from backend.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def admin_client(client):
    r = await client.post("/api/auth/login", json={"password": "testpass"})
    assert r.status_code == 200
    client.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    yield client
