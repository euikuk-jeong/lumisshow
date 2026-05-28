import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.models.database import init_db
from backend.routers import admin_albums, admin_browse, admin_links, auth, media, share

_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
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
