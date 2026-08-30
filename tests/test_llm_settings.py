from backend.services import llm_settings


def test_encrypt_decrypt_roundtrip(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "roundtrip-secret")
    enc = llm_settings.encrypt_api_key("sk-test-1234")
    assert enc != "sk-test-1234"
    assert llm_settings.decrypt_api_key(enc) == "sk-test-1234"


def test_decrypt_degrades_gracefully_with_wrong_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret-a")
    enc = llm_settings.encrypt_api_key("sk-test-5678")
    monkeypatch.setenv("JWT_SECRET", "secret-b")
    assert llm_settings.decrypt_api_key(enc) is None


def test_decrypt_degrades_gracefully_on_garbage_input(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret-c")
    assert llm_settings.decrypt_api_key("not-a-valid-fernet-token") is None
