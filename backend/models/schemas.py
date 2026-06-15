import json
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


def parse_music_paths(raw: str | None) -> list[str]:
    if not raw:
        return []
    if raw.startswith('['):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return []
    return [raw]


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Browse ────────────────────────────────────────────────────────────────────

class FolderItem(BaseModel):
    path: str
    name: str
    child_count: int

class PhotoItem(BaseModel):
    path: str
    name: str
    size: int
    taken_at: Optional[datetime]
    width: Optional[int]
    height: Optional[int]
    thumb_url: Optional[str]

class BrowseResponse(BaseModel):
    folders: list[FolderItem]
    photos: list[PhotoItem]

class SearchResponse(BaseModel):
    items: list[PhotoItem]
    total: int
    page: int


# ── Albums ────────────────────────────────────────────────────────────────────

class AlbumCreate(BaseModel):
    name: str
    description: Optional[str] = None
    photo_paths: list[str] = []

class AlbumUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    cover_path: Optional[str] = None
    music_paths: Optional[list[str]] = None

class AlbumPhotoResponse(BaseModel):
    id: int
    album_id: int
    file_path: str
    sort_order: int
    added_at: datetime

class AlbumResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    cover_path: Optional[str]
    music_paths: list[str]
    photo_count: int
    created_at: datetime
    updated_at: datetime

class AlbumDetail(AlbumResponse):
    photos: list[AlbumPhotoResponse]


# ── Album Photos ──────────────────────────────────────────────────────────────

class PhotoPathsRequest(BaseModel):
    photo_paths: list[str]

class PhotoOrderItem(BaseModel):
    id: int
    sort_order: int

class PhotoOrderRequest(BaseModel):
    orders: list[PhotoOrderItem]


# ── Share Links ───────────────────────────────────────────────────────────────

class LinkCreate(BaseModel):
    password: Optional[str] = None
    expires_at: Optional[datetime] = None

class LinkUpdate(BaseModel):
    is_active: Optional[bool] = None
    expires_at: Optional[datetime] = None
    password: Optional[str] = None

class LinkResponse(BaseModel):
    id: int
    token: str
    share_url: str
    has_password: bool
    expires_at: Optional[datetime]
    is_active: bool
    created_at: datetime


# ── Share (public viewer) ─────────────────────────────────────────────────────

class ShareAuthRequest(BaseModel):
    password: Optional[str] = None

class ShareAlbumResponse(BaseModel):
    album_name: str
    description: Optional[str]
    photo_count: int
    created_at: datetime
    expires_at: Optional[datetime]
    has_music: bool
    music_count: int
    music_names: list[str]

class SharePhotoItem(BaseModel):
    id: int
    url: str
    thumb_small_url: str
    thumb_medium_url: str
    filename: Optional[str]
    taken_at: Optional[datetime]
    width: Optional[int]
    height: Optional[int]
    make: Optional[str]
    camera: Optional[str]
    software: Optional[str]
    shutter: Optional[str]
    aperture: Optional[str]
    iso: Optional[int]
    focal_length: Optional[str]
    shoot_mode: Optional[str]
    flash: Optional[str]
    metering: Optional[str]
    exposure_mode: Optional[str]

class SharePhotosResponse(BaseModel):
    photos: list[SharePhotoItem]
    total: int
