import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

_ALGORITHM = "HS256"
_ADMIN_JWT_EXPIRE_HOURS = 8
_SHARE_SESSION_EXPIRE_HOURS = 24

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer()


def _secret() -> str:
    return os.getenv("JWT_SECRET", "dev_secret_key")


# ── 비밀번호 ──────────────────────────────────────────────────────────────────

def verify_admin_password(plain: str) -> bool:
    return plain == os.getenv("ADMIN_PASSWORD", "dev_password")

def hash_password(plain: str) -> str:
    return _pwd.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


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


def get_share_session_verifier(share_token: str):
    async def _verify(
        cred: HTTPAuthorizationCredentials = Depends(_bearer),
    ) -> str:
        try:
            payload = _decode(cred.credentials)
            if payload.get("sub") != f"share:{share_token}":
                raise ValueError
        except (JWTError, ValueError):
            raise HTTPException(status_code=401, detail="Invalid share session")
        return share_token
    return _verify
