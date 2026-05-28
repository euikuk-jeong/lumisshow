import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt as _bcrypt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

_ALGORITHM = "HS256"
_ADMIN_JWT_EXPIRE_HOURS = 8
_SHARE_SESSION_EXPIRE_HOURS = 24

_bearer = HTTPBearer()


def _secret() -> str:
    return os.getenv("JWT_SECRET", "dev_secret_key")


# ── 비밀번호 ──────────────────────────────────────────────────────────────────

def verify_admin_password(plain: str) -> bool:
    expected = os.getenv("ADMIN_PASSWORD", "dev_password")
    return hmac.compare_digest(plain.encode(), expected.encode())

def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_admin_token() -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=_ADMIN_JWT_EXPIRE_HOURS)
    return jwt.encode({"sub": "admin", "exp": exp}, _secret(), algorithm=_ALGORITHM)

def create_share_session_token(token: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=_SHARE_SESSION_EXPIRE_HOURS)
    return jwt.encode({"sub": f"share:{token}", "exp": exp}, _secret(), algorithm=_ALGORITHM)

def _decode(raw: str) -> dict:
    return jwt.decode(raw, _secret(), algorithms=[_ALGORITHM])


# ── FastAPI 의존성 ─────────────────────────────────────────────────────────────

async def get_current_admin(
    cred: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    try:
        payload = _decode(cred.credentials)
        if payload.get("sub") != "admin":
            raise ValueError
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return "admin"


def verify_share_session_cookie(share_token: str, cookie: Optional[str]) -> None:
    """httpOnly 쿠키 기반 공유 세션 검증. 실패 시 HTTPException(401) 발생."""
    if not cookie:
        raise HTTPException(status_code=401, detail="Share session required")
    try:
        payload = _decode(cookie)
        if payload.get("sub") != f"share:{share_token}":
            raise ValueError
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid share session")


def get_share_token_from_cookie(cookie: Optional[str]) -> str:
    """쿠키에서 share token 추출. 실패 시 HTTPException(401)."""
    if not cookie:
        raise HTTPException(status_code=401, detail="Share session required")
    try:
        payload = _decode(cookie)
        sub = payload.get("sub", "")
        if not sub.startswith("share:"):
            raise ValueError
        return sub[len("share:"):]
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid share session")
