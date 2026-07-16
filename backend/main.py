import html as _html
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from backend.models.ai_database import init_ai_db
from backend.models.database import close_db_pool, get_db, init_db
from backend.routers import admin_albums, admin_browse, admin_links, admin_people, admin_settings, auth, media, share

_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
_logger = logging.getLogger(__name__)
_INSECURE_DEFAULTS = {"dev_secret_key", "dev_password"}
APP_VERSION = os.getenv("APP_VERSION", "dev")


def _validate_env() -> None:
    issues = []
    if os.getenv("JWT_SECRET", "dev_secret_key") in _INSECURE_DEFAULTS:
        issues.append("JWT_SECRET")
    if not os.getenv("ADMIN_PASSWORD_HASH") and os.getenv("ADMIN_PASSWORD", "dev_password") in _INSECURE_DEFAULTS:
        issues.append("ADMIN_PASSWORD")
    if issues:
        _logger.warning(
            "INSECURE CONFIGURATION: %s use default dev values — set secure values before production use.",
            ", ".join(issues),
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_env()
    await init_db()
    await init_ai_db()
    yield
    await close_db_pool()


app = FastAPI(title="LumisShow", version=APP_VERSION, lifespan=lifespan)


@app.middleware("http")
async def _security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


app.include_router(auth.router)
app.include_router(admin_browse.router)
app.include_router(admin_albums.router)
app.include_router(admin_links.router)
app.include_router(admin_people.router)
app.include_router(admin_settings.router)
app.include_router(share.router)
app.include_router(media.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"version": APP_VERSION}


# 정적 파일 서빙 (frontend assets)
_assets_dir = _FRONTEND_DIR / "assets"
if _assets_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")


# SPA 라우트: /admin/* → index.html
@app.get("/admin/{full_path:path}")
async def admin_spa(full_path: str):
    index = _FRONTEND_DIR / "index.html"
    if index.is_file():
        return FileResponse(str(index))
    return {"message": "Frontend not yet implemented"}


# SPA 라우트: /s/{token}/* → OG 메타 태그 주입된 index.html
@app.get("/s/{full_path:path}")
async def share_spa(full_path: str, db=Depends(get_db)):
    index = _FRONTEND_DIR / "index.html"
    if not index.is_file():
        return {"message": "Frontend not yet implemented"}

    html_content = index.read_text(encoding="utf-8")
    token = full_path.split("/")[0]

    if token:
        try:
            async with db.execute(
                """
                SELECT a.name, a.description, sl.password_hash, COUNT(ap.id) AS photo_count
                FROM share_links sl
                JOIN albums a ON a.id = sl.album_id
                LEFT JOIN album_photos ap ON ap.album_id = a.id
                WHERE sl.token = ? AND sl.is_active = 1
                  AND (sl.expires_at IS NULL OR sl.expires_at > datetime('now'))
                GROUP BY a.id
                """,
                (token,),
            ) as cur:
                row = await cur.fetchone()
        except Exception:
            _logger.exception("share_spa: failed to load OG meta for token %s", token)
            row = None

        if row:
            base_url = os.getenv("BASE_URL", "").rstrip("/")
            title = row["name"] or "LumisShow"
            desc_parts = []
            if row["description"]:
                desc_parts.append(row["description"])
            desc_parts.append(f"사진 {row['photo_count']}장")
            description = " · ".join(desc_parts)

            og_lines = [
                f'  <meta property="og:title" content="{_html.escape(title)}" />',
                f'  <meta property="og:description" content="{_html.escape(description)}" />',
                '  <meta property="og:type" content="website" />',
                '  <meta property="og:site_name" content="LumisShow" />',
            ]
            if base_url:
                # 패스워드 보호 앨범은 커버 이미지를 노출하지 않음 (제목/설명은 유지)
                if row["password_hash"] is None:
                    og_lines += [
                        f'  <meta property="og:image" content="{base_url}/api/share/{token}/og-image" />',
                        '  <meta property="og:image:width" content="800" />',
                        '  <meta property="og:image:height" content="600" />',
                    ]
                og_lines.append(f'  <meta property="og:url" content="{base_url}/s/{token}" />')
            og_block = "\n".join(og_lines) + "\n"
            html_content = html_content.replace("</head>", og_block + "</head>", 1)

    return HTMLResponse(html_content)


# SPA 진입점
@app.get("/")
async def root():
    index = _FRONTEND_DIR / "index.html"
    if index.is_file():
        return FileResponse(str(index))
    return {"message": "LumisShow API"}
