import asyncio
import os
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from backend.models.database import get_db
from backend.models.schemas import LoginRequest, TokenResponse
from backend.services.auth import create_admin_token, get_current_admin, verify_admin_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

_ADMIN_IMG_COOKIE = "admin_img_session"
_ADMIN_IMG_COOKIE_MAX_AGE = 8 * 3600

# Reuses share_link_failures table with "admin:{ip}" key prefix
_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 15 * 60


def _admin_key(request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"admin:{ip}"


async def _check_admin_lockout(key: str, db) -> None:
    async with db.execute(
        "SELECT fail_count, locked_until FROM share_link_failures WHERE token = ?", (key,)
    ) as cur:
        row = await cur.fetchone()
    if row and row["fail_count"] >= _MAX_ATTEMPTS:
        if time.time() < row["locked_until"]:
            raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")
        await db.execute("DELETE FROM share_link_failures WHERE token = ?", (key,))
        await db.commit()


async def _record_admin_failure(key: str, db) -> None:
    now = time.time()
    async with db.execute(
        "SELECT fail_count FROM share_link_failures WHERE token = ?", (key,)
    ) as cur:
        row = await cur.fetchone()
    count = (row["fail_count"] if row else 0) + 1
    locked_until = now + _LOCKOUT_SECONDS if count >= _MAX_ATTEMPTS else 0.0
    await db.execute(
        "INSERT OR REPLACE INTO share_link_failures (token, fail_count, locked_until, recorded_at) VALUES (?, ?, ?, ?)",
        (key, count, locked_until, now),
    )
    await db.commit()


async def _clear_admin_failures(key: str, db) -> None:
    await db.execute("DELETE FROM share_link_failures WHERE token = ?", (key,))
    await db.commit()


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request, response: Response, db=Depends(get_db)):
    key = _admin_key(request)
    await _check_admin_lockout(key, db)
    if not await asyncio.to_thread(verify_admin_password, req.password):
        await _record_admin_failure(key, db)
        raise HTTPException(status_code=401, detail="Invalid password")
    await _clear_admin_failures(key, db)
    token = create_admin_token()
    response.set_cookie(
        key=_ADMIN_IMG_COOKIE,
        value=token,
        httponly=True,
        max_age=_ADMIN_IMG_COOKIE_MAX_AGE,
        samesite="lax",
        secure=os.getenv("BASE_URL", "").startswith("https://"),
        path="/api/admin",
    )
    return TokenResponse(access_token=token)


@router.post("/logout")
async def logout(response: Response, _: str = Depends(get_current_admin)):
    response.delete_cookie(key=_ADMIN_IMG_COOKIE, path="/api/admin")
    return {"detail": "logged out"}


@router.get("/me")
async def me(admin: str = Depends(get_current_admin)):
    return {"user": admin}
