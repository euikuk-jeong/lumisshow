import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.models.database import init_db
from backend.routers import admin_albums, admin_browse, admin_links, auth, media, share


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
