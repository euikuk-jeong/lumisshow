"""OpenAI 호환 / Anthropic LLM 직접 호출 — SDK 없이 requests 사용.

동기(requests) 호출이라 async 라우터에서 그대로 부르면 이벤트 루프를 5~30초 붙잡아
/thumb·/media·공유뷰어 전체가 멈춘다 — 호출부는 반드시 starlette.concurrency.run_in_threadpool
로 감싸야 한다(services/xmp_export.py가 동기 조립을 run_in_executor로 스레드 오프로드하는
것과 동일한 이유).
"""

import json
import re
from typing import Optional

import requests

_TIMEOUT = 20
_DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
_DEFAULT_ANTHROPIC_MODEL = "claude-3-5-haiku-latest"


class LlmError(Exception):
    """사용자에게 그대로 보여줄 수 있는 한국어 메시지를 담는다."""


def _error_detail(resp: Optional["requests.Response"]) -> str:
    """provider가 돌려준 실제 에러 본문(예: "모델이 과부하 상태입니다")을 최대한 뽑아낸다.

    requests.HTTPError의 기본 str()은 상태코드/URL만 담고 본문은 버려서, "503 Server
    Error"처럼 원인을 알 수 없는 메시지만 사용자에게 보이는 문제가 있었다 — provider가
    JSON으로 {"error": {"message": ...}}를 주면 그걸, 아니면 응답 본문 앞부분을 덧붙인다.
    """
    if resp is None:
        return ""
    try:
        body = resp.json()
        message = body.get("error", {}).get("message") if isinstance(body, dict) else None
        if not message and isinstance(body, list) and body:
            message = body[0].get("error", {}).get("message")
        if message:
            return str(message)
    except (ValueError, AttributeError):
        pass
    text = (resp.text or "").strip()
    return text[:200] if text else ""


def _openai_compatible_chat(base_url: str, api_key: str, model: str, prompt: str) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.HTTPError as e:
        detail = _error_detail(e.response)
        raise LlmError(f"LLM 호출 실패: {e}" + (f" — {detail}" if detail else "")) from e
    except requests.RequestException as e:
        raise LlmError(f"LLM 호출 실패: {e}") from e
    try:
        return resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise LlmError("LLM 응답 형식을 해석하지 못했습니다") from e


def _anthropic_messages(api_key: str, model: str, prompt: str) -> str:
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 500,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.HTTPError as e:
        detail = _error_detail(e.response)
        raise LlmError(f"LLM 호출 실패: {e}" + (f" — {detail}" if detail else "")) from e
    except requests.RequestException as e:
        raise LlmError(f"LLM 호출 실패: {e}") from e
    try:
        return resp.json()["content"][0]["text"]
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise LlmError("LLM 응답 형식을 해석하지 못했습니다") from e


def call_llm(config: dict, prompt: str) -> str:
    """config: {provider, base_url, model, api_key}. 동기 함수 — run_in_threadpool로 호출할 것."""
    provider = config["provider"]
    api_key = config["api_key"]
    model = config.get("model") or None
    if provider == "anthropic":
        return _anthropic_messages(api_key, model or _DEFAULT_ANTHROPIC_MODEL, prompt)
    if provider == "openai_compatible":
        raw_base_url = config.get("base_url")
        if raw_base_url and not model:
            # 커스텀 base_url(Gemini/Ollama 등)에서는 OpenAI 기본 모델명이 존재하지 않아
            # 원격 서버가 404를 반환한다 — 그 혼란스러운 원격 오류 대신 원인을 바로 알려준다.
            raise LlmError("커스텀 Base URL을 사용할 때는 모델명을 반드시 입력해야 합니다")
        base_url = raw_base_url or "https://api.openai.com/v1"
        return _openai_compatible_chat(base_url, api_key, model or _DEFAULT_OPENAI_MODEL, prompt)
    raise LlmError(f"알 수 없는 provider: {provider}")


def extract_json(text: str) -> Optional[dict]:
    """관대한 JSON 파싱 — 마크다운 코드펜스 등에 감싸져 와도 첫 {...} 블록을 추출."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
