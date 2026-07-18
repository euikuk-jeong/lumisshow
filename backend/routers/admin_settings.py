import json

from fastapi import APIRouter, Depends

from backend.models.database import get_db
from backend.models.schemas import SettingsResponse, SettingsUpdate
from backend.services.auth import get_current_admin
from backend.services.settings import get_settings

router = APIRouter(prefix="/api/admin/settings", tags=["admin-settings"])


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
