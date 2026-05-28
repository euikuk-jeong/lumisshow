import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.models.database import init_db
from backend.routers import admin_albums, admin_browse, admin_links, auth, media, share

_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
_logger = logging.getLogger(__name__)
_INSECURE_DEFAULTS = {"dev_secret_key", "dev_password"}


def _validate_env() -> None:
    issues = [
        name
        for name, key, default in [
            ("JWT_SECRET", "JWT_SECRET", "dev_secret_key"),
            ("ADMIN_PASSWORD", "ADMIN_PASSWORD", "dev_password"),
        ]
        if os.getenv(key, default) in _INSECURE_DEFAULTS
    ]
    if issues:
        _logger.warning(
            "INSECURE CONFIGURATION: %s use default dev values — set secure values before production use.",
            ", ".join(issues),
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_env()
    await init_db()
    yield


app = FastAPI(title="LumisShow", version="0.1.0", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(admin_browse.router)
app.include_router(admin_albums.router)
app.include_router(admin_links.router)
app.include_router(share.router)
app.include_router(media.router)


@app.get("/health")
def health():
    return {"status": "ok"}


# 정적 파일 서빙 (frontend assets)
_assets_dir = _FRONTEND_DIR / "assets"
if _assets_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")


# SPA 라우트: /s/{token}/* → index.html
@app.get("/s/{full_path:path}")
async def share_spa(full_path: str):
    index = _FRONTEND_DIR / "index.html"
    if index.is_file():
        return FileResponse(str(index))
    return {"message": "Frontend not yet implemented"}


# SPA 진입점
@app.get("/")
async def root():
    index = _FRONTEND_DIR / "index.html"
    if index.is_file():
        return FileResponse(str(index))
    return {"message": "LumisShow API"}
