import os

from backend.services import album_style_suggest as suggest_mod
from backend.services.llm_client import LlmError


# ── GET/PATCH /api/admin/llm/settings ───────────────────────────────────────

async def test_get_llm_settings_defaults(admin_client):
    r = await admin_client.get("/api/admin/llm/settings")
    assert r.status_code == 200
    data = r.json()
    assert data["provider"] is None
    assert data["api_key_set"] is False


async def test_get_llm_settings_requires_auth(client):
    r = await client.get("/api/admin/llm/settings")
    assert r.status_code == 401


async def test_patch_llm_settings_sets_provider_and_key(admin_client):
    r = await admin_client.patch("/api/admin/llm/settings", json={
        "provider": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "api_key": "sk-secret-abc",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["provider"] == "openai_compatible"
    assert data["base_url"] == "https://api.openai.com/v1"
    assert data["model"] == "gpt-4o-mini"
    assert data["api_key_set"] is True
    assert "api_key" not in data  # 원문/암호문 절대 되돌려주지 않음


async def test_patch_llm_settings_openai_compatible_requires_base_url(admin_client):
    r = await admin_client.patch("/api/admin/llm/settings", json={
        "provider": "openai_compatible",
        "base_url": "",
        "api_key": "sk-x",
    })
    assert r.status_code == 422


async def test_patch_llm_settings_clears_key_with_empty_string(admin_client):
    await admin_client.patch("/api/admin/llm/settings", json={"provider": "anthropic", "api_key": "sk-1"})
    r = await admin_client.patch("/api/admin/llm/settings", json={"api_key": ""})
    assert r.status_code == 200
    assert r.json()["api_key_set"] is False


async def test_delete_llm_settings_resets_everything(admin_client):
    await admin_client.patch("/api/admin/llm/settings", json={
        "provider": "openai_compatible",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-3.6-flash",
        "api_key": "sk-1",
    })
    r = await admin_client.delete("/api/admin/llm/settings")
    assert r.status_code == 200
    data = r.json()
    assert data["provider"] is None
    assert data["base_url"] is None
    assert data["model"] is None
    assert data["api_key_set"] is False

    r2 = await admin_client.get("/api/admin/llm/settings")
    assert r2.json() == data


async def test_delete_llm_settings_requires_auth(client):
    r = await client.delete("/api/admin/llm/settings")
    assert r.status_code == 401


async def test_patch_llm_settings_requires_auth(client):
    r = await client.patch("/api/admin/llm/settings", json={"provider": "anthropic"})
    assert r.status_code == 401


# ── POST /api/admin/llm/settings/test ───────────────────────────────────────

async def test_connection_test_without_config(admin_client):
    r = await admin_client.post("/api/admin/llm/settings/test")
    assert r.status_code == 200
    assert r.json()["ok"] is False


async def test_connection_test_calls_llm(admin_client, monkeypatch):
    await admin_client.patch("/api/admin/llm/settings", json={
        "provider": "anthropic", "model": "claude-3-5-haiku-latest", "api_key": "sk-1",
    })
    monkeypatch.setattr("backend.routers.admin_llm.call_llm", lambda config, prompt: "ok")
    r = await admin_client.post("/api/admin/llm/settings/test")
    assert r.status_code == 200
    assert r.json()["ok"] is True


async def test_connection_test_reports_llm_error(admin_client, monkeypatch):
    await admin_client.patch("/api/admin/llm/settings", json={"provider": "anthropic", "api_key": "sk-1"})

    def _raise(config, prompt):
        raise LlmError("연결 실패")

    monkeypatch.setattr("backend.routers.admin_llm.call_llm", _raise)
    r = await admin_client.post("/api/admin/llm/settings/test")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert data["message"] == "연결 실패"


# ── POST /api/admin/llm/suggest-style ───────────────────────────────────────

async def test_suggest_style_requires_configuration(admin_client):
    r = await admin_client.post("/api/admin/llm/suggest-style", json={"name": "제주도 여행"})
    assert r.status_code == 409


async def test_suggest_style_rejects_empty_name(admin_client):
    r = await admin_client.post("/api/admin/llm/suggest-style", json={"name": ""})
    assert r.status_code == 422


async def test_suggest_style_applies_allowlist_and_reads_bundled_file(admin_client, monkeypatch):
    await admin_client.patch("/api/admin/llm/settings", json={"provider": "anthropic", "api_key": "sk-1"})

    data_dir = os.environ["DATA_DIR"]
    bundled_dir = os.path.join(data_dir, "music", "bundled")
    os.makedirs(bundled_dir, exist_ok=True)
    known_file = "alex-morgan-calm-piano-541028.mp3"
    open(os.path.join(bundled_dir, known_file), "wb").close()

    monkeypatch.setattr(
        suggest_mod, "call_llm",
        lambda config, prompt: (
            '{"music_id": "%s", "theme_id": "sepia", "font_id": "not-a-real-font", "reason": "차분한 앨범"}'
            % known_file
        ),
    )
    r = await admin_client.post(
        "/api/admin/llm/suggest-style", json={"name": "제주도 여행", "description": "가족 여행"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["music_path"].endswith(known_file)
    assert data["ui_theme"] == "sepia"
    assert data["title_font"] is None  # 후보 목록에 없는 값은 무시
    assert data["reason"] == "차분한 앨범"


async def test_suggest_style_skips_music_when_file_missing_on_disk(admin_client, monkeypatch):
    await admin_client.patch("/api/admin/llm/settings", json={"provider": "anthropic", "api_key": "sk-1"})
    monkeypatch.setattr(
        suggest_mod, "call_llm",
        lambda config, prompt: (
            '{"music_id": "alex-morgan-calm-piano-541028.mp3", "theme_id": "dark", '
            '"font_id": "jua", "reason": "명랑"}'
        ),
    )
    r = await admin_client.post("/api/admin/llm/suggest-style", json={"name": "생일파티"})
    assert r.status_code == 200
    data = r.json()
    assert data["music_path"] is None  # 파일 없음 → 그 필드만 무시
    assert data["ui_theme"] == "dark"
    assert data["title_font"] == "jua"


async def test_suggest_style_total_parse_failure_returns_502(admin_client, monkeypatch):
    await admin_client.patch("/api/admin/llm/settings", json={"provider": "anthropic", "api_key": "sk-1"})
    monkeypatch.setattr(suggest_mod, "call_llm", lambda config, prompt: "이건 자유 텍스트입니다, JSON 아님")
    r = await admin_client.post("/api/admin/llm/suggest-style", json={"name": "테스트"})
    assert r.status_code == 502
    assert "해석" in r.json()["detail"]
