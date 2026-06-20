import json

from fastapi import APIRouter, Depends

from backend.models.database import get_db
from backend.models.schemas import SettingsResponse, SettingsUpdate
from backend.services.auth import get_current_admin

router = APIRouter(prefix="/api/admin/settings", tags=["admin-settings"])

DEFAULTS: dict = {
    "timezone_offset": 0,
    "timezone_label": "UTC+0 (UTC)",
    "slideshow_interval": 5,
    "slideshow_order": "sequential",
    "slideshow_effect": "random",
    "slideshow_music": True,
    "slideshow_volume": 25,
    "slideshow_loop": True,
    "browse_hidden_paths": [],
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


@router.get("", response_model=SettingsResponse)
async def read_settings(
    _: str = Depends(get_current_admin),
    db=Depends(get_db),
):
    return await get_settings(db)


@router.patch("", response_model=SettingsResponse)
async def update_settings(
    body: SettingsUpdate,
    _: str = Depends(get_current_admin),
    db=Depends(get_db),
):
    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, json.dumps(value)),
        )
    if updates:
        await db.commit()
    return await get_settings(db)
