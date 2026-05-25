import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.models.database import init_db
from backend.routers import auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="LumisShow", version="0.1.0", lifespan=lifespan)

app.include_router(auth.router)


@app.get("/health")
def health():
    return {"status": "ok"}
