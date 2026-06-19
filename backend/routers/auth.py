import os

from fastapi import APIRouter, Depends, HTTPException, Response

from backend.models.schemas import LoginRequest, TokenResponse
from backend.services.auth import create_admin_token, get_current_admin, verify_admin_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

_ADMIN_IMG_COOKIE = "admin_img_session"
_ADMIN_IMG_COOKIE_MAX_AGE = 8 * 3600


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, response: Response):
    if not verify_admin_password(req.password):
        raise HTTPException(status_code=401, detail="Invalid password")
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
