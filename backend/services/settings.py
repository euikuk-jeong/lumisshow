"""settings 테이블 조회 — admin_settings 라우터 + admin_browse/admin_albums/share 공용."""

import json

DEFAULTS: dict = {
    "site_title": "LumisShow",
    "timezone_offset": 0,
    "timezone_label": "UTC+0 (UTC)",
    "slideshow_interval": 5,
    "slideshow_order": "sequential",
    "slideshow_effect": "random",
    "slideshow_music": True,
    "slideshow_volume": 25,
    "slideshow_loop": True,
    "browse_hidden_paths": [],
    "ui_theme": "dark",
}


async def get_settings(db) -> dict:
    async with db.execute("SELECT key, value FROM settings") as cur:
        rows = await cur.fetchall()
    result = {**DEFAULTS}
    for row in rows:
        if row["key"] in result:
            try:
                result[row["key"]] = json.loads(row["value"])
            except (json.JSONDecodeError, ValueError):
                pass
    return result
