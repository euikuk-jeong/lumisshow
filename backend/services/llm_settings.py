"""LLM(음악·테마·폰트 추천) provider 설정 — JWT_SECRET 기반 대칭키로 API 키 암호화 저장.

settings 테이블(services/settings.py)을 그대로 재사용하되 DEFAULTS에는 올리지 않는다 —
DEFAULTS에 있으면 GET /api/admin/settings가 암호화된 키 blob까지 그대로 프론트에
내려보내게 된다. 이 모듈이 직접 SELECT로 읽고, 공개 조회(get_llm_settings)는
api_key_set 불리언만 반환하며 원문/암호문 모두 내보내지 않는다.
"""

import base64
import hashlib
import json
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

_KEYS = ("llm_provider", "llm_base_url", "llm_model", "llm_api_key_enc")


def _fernet() -> Fernet:
    secret = os.getenv("JWT_SECRET", "dev_secret_key").encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def encrypt_api_key(raw: str) -> str:
    return _fernet().encrypt(raw.encode("utf-8")).decode("ascii")


def decrypt_api_key(enc: str) -> Optional[str]:
    """복호화 실패(JWT_SECRET 변경 등) 시 None — 호출자는 '키를 재등록하세요'로 처리, 500 아님."""
    try:
        return _fernet().decrypt(enc.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


async def _read_raw(db) -> dict:
    placeholders = ",".join("?" * len(_KEYS))
    async with db.execute(
        f"SELECT key, value FROM settings WHERE key IN ({placeholders})", _KEYS
    ) as cur:
        rows = await cur.fetchall()
    result: dict = {}
    for row in rows:
        try:
            result[row["key"]] = json.loads(row["value"])
        except (json.JSONDecodeError, ValueError):
            pass
    return result


async def get_llm_settings(db) -> dict:
    """공개 조회용 — provider/base_url/model + api_key_set(bool)만 반환."""
    raw = await _read_raw(db)
    return {
        "provider": raw.get("llm_provider"),
        "base_url": raw.get("llm_base_url"),
        "model": raw.get("llm_model"),
        "api_key_set": bool(raw.get("llm_api_key_enc")),
    }


async def get_decrypted_config(db) -> Optional[dict]:
    """내부 호출(연결 테스트/추천)용 — 원문 API 키 포함.

    provider 미설정이거나 키가 없거나 복호화 실패면 None(호출자는 409/설정 없음으로 처리).
    """
    raw = await _read_raw(db)
    provider = raw.get("llm_provider")
    enc = raw.get("llm_api_key_enc")
    if not provider or not enc:
        return None
    api_key = decrypt_api_key(enc)
    if api_key is None:
        return None
    return {
        "provider": provider,
        "base_url": raw.get("llm_base_url"),
        "model": raw.get("llm_model"),
        "api_key": api_key,
    }


async def update_llm_settings(
    db,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> None:
    updates: dict = {}
    if provider is not None:
        updates["llm_provider"] = provider
    if base_url is not None:
        updates["llm_base_url"] = base_url
    if model is not None:
        updates["llm_model"] = model
    if api_key is not None:
        # 빈 문자열 = 키 삭제(재등록 전까지 미설정 취급), 그 외 = 암호화 저장
        updates["llm_api_key_enc"] = None if api_key == "" else encrypt_api_key(api_key)
    for key, value in updates.items():
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, json.dumps(value)),
        )
    if updates:
        await db.commit()


async def reset_llm_settings(db) -> None:
    """provider/base_url/model/API 키 전부 제거 — settings 테이블에서 행 자체를 삭제.

    PATCH의 "None = 변경 안 함" 관례로는 provider/base_url/model을 지울 방법이 없어
    (그 필드들은 빈 문자열 관례도 없음) 별도 삭제 경로가 필요하다.
    """
    placeholders = ",".join("?" * len(_KEYS))
    await db.execute(f"DELETE FROM settings WHERE key IN ({placeholders})", _KEYS)
    await db.commit()
