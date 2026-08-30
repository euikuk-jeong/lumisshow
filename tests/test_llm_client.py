import pytest
import requests

from backend.services import llm_client
from backend.services.llm_client import LlmError, call_llm


class _FakeResponse:
    """requests.Response 흉내 — raise_for_status()가 던지는 HTTPError에 .response로 실린다."""

    def __init__(self, status_code, json_body=None, text_body=""):
        self.status_code = status_code
        self._json_body = json_body
        self.text = text_body

    def json(self):
        if self._json_body is None:
            raise ValueError("no json body")
        return self._json_body

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.HTTPError(f"{self.status_code} Server Error: x for url: y")
            err.response = self
            raise err


def test_openai_compatible_requires_model_with_custom_base_url():
    config = {"provider": "openai_compatible", "base_url": "https://example.com/v1", "api_key": "k", "model": None}
    with pytest.raises(LlmError, match="모델명"):
        call_llm(config, "prompt")


def test_openai_compatible_defaults_model_for_real_openai(monkeypatch):
    captured = {}

    def fake_chat(base_url, api_key, model, prompt):
        captured.update(base_url=base_url, model=model)
        return "ok"

    monkeypatch.setattr(llm_client, "_openai_compatible_chat", fake_chat)
    config = {"provider": "openai_compatible", "base_url": None, "api_key": "k", "model": None}
    assert call_llm(config, "prompt") == "ok"
    assert captured["base_url"] == "https://api.openai.com/v1"
    assert captured["model"] == "gpt-4o-mini"


def test_openai_compatible_uses_explicit_model_with_custom_base_url(monkeypatch):
    captured = {}

    def fake_chat(base_url, api_key, model, prompt):
        captured.update(base_url=base_url, model=model)
        return "ok"

    monkeypatch.setattr(llm_client, "_openai_compatible_chat", fake_chat)
    config = {
        "provider": "openai_compatible",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "api_key": "k",
        "model": "gemini-2.0-flash",
    }
    assert call_llm(config, "prompt") == "ok"
    assert captured["model"] == "gemini-2.0-flash"


# ── 에러 본문 노출: "503 Server Error"만으로는 원인을 알 수 없어(실제로 겪은 문제 —
#    Gemini가 모델 과부하일 때 503을 주는데 기본 requests 메시지는 이유를 안 알려줌)
#    provider가 돌려준 실제 메시지를 최대한 덧붙인다. ──

def test_openai_compatible_surfaces_gemini_style_error_detail(monkeypatch):
    fake_resp = _FakeResponse(503, json_body={
        "error": {"code": 503, "message": "The model is overloaded. Please try again later.", "status": "UNAVAILABLE"},
    })
    monkeypatch.setattr(llm_client.requests, "post", lambda *a, **k: fake_resp)
    with pytest.raises(LlmError, match="overloaded"):
        call_llm(
            {"provider": "openai_compatible", "base_url": "https://example.com/v1", "model": "m", "api_key": "k"},
            "prompt",
        )


def test_openai_compatible_surfaces_list_wrapped_error_detail(monkeypatch):
    # Gemini의 OpenAI 호환 레이어는 에러를 최상위 배열로 감싸서 줄 때가 있다([{"error": {...}}]).
    fake_resp = _FakeResponse(400, json_body=[{"error": {"message": "Please pass a valid API key"}}])
    monkeypatch.setattr(llm_client.requests, "post", lambda *a, **k: fake_resp)
    with pytest.raises(LlmError, match="valid API key"):
        call_llm(
            {"provider": "openai_compatible", "base_url": "https://example.com/v1", "model": "m", "api_key": "k"},
            "prompt",
        )


def test_openai_compatible_falls_back_to_raw_text_when_not_json(monkeypatch):
    fake_resp = _FakeResponse(500, json_body=None, text_body="upstream connect error")
    monkeypatch.setattr(llm_client.requests, "post", lambda *a, **k: fake_resp)
    with pytest.raises(LlmError, match="upstream connect error"):
        call_llm(
            {"provider": "openai_compatible", "base_url": "https://example.com/v1", "model": "m", "api_key": "k"},
            "prompt",
        )


def test_anthropic_surfaces_error_detail(monkeypatch):
    fake_resp = _FakeResponse(401, json_body={"error": {"message": "invalid x-api-key"}})
    monkeypatch.setattr(llm_client.requests, "post", lambda *a, **k: fake_resp)
    with pytest.raises(LlmError, match="invalid x-api-key"):
        call_llm({"provider": "anthropic", "api_key": "k", "model": "m"}, "prompt")
