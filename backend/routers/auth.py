from fastapi import APIRouter, HTTPException

from backend.models.schemas import LoginRequest, TokenResponse
from backend.services.auth import create_admin_token, get_current_admin, verify_admin_password
from fastapi import Depends

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    if not verify_admin_password(req.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    return TokenResponse(access_token=create_admin_token())


@router.post("/logout")
async def logout(_: str = Depends(get_current_admin)):
    # JWT는 stateless — 클라이언트가 토큰을 버리면 로그아웃
    return {"detail": "logged out"}


@router.get("/me")
async def me(admin: str = Depends(get_current_admin)):
    return {"user": admin}
