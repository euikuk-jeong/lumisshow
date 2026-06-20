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
    slideshow_interval: Optional[int] = None
    slideshow_order: Optional[str] = None
    slideshow_effect: Optional[str] = None
    slideshow_music: Optional[bool] = None
    slideshow_volume: Optional[int] = None
    slideshow_loop: Optional[bool] = None
    photo_sort_by: Optional[str] = None
    photo_sort_dir: Optional[str] = None

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
    first_photo_path: Optional[str] = None
    music_paths: list[str]
    photo_count: int
    view_count: int = 0
    created_at: datetime
    updated_at: datetime
    slideshow_interval: int = 5
    slideshow_order: str = "sequential"
    slideshow_effect: str = "random"
    slideshow_music: bool = True
    slideshow_volume: int = 25
    slideshow_loop: bool = True
    photo_sort_by: str = "taken_at"
    photo_sort_dir: str = "asc"

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


# ── Settings ──────────────────────────────────────────────────────────────────

class SlideshowDefaults(BaseModel):
    interval: int
    order: str
    effect: str
    music: bool
    volume: int
    loop: bool

class SettingsResponse(BaseModel):
    timezone_offset: int
    timezone_label: str
    slideshow_interval: int
    slideshow_order: str
    slideshow_effect: str
    slideshow_music: bool
    slideshow_volume: int
    slideshow_loop: bool
    browse_hidden_paths: list[str] = []

class SettingsUpdate(BaseModel):
    timezone_offset: Optional[int] = None
    timezone_label: Optional[str] = None
    slideshow_interval: Optional[int] = None
    slideshow_order: Optional[str] = None
    slideshow_effect: Optional[str] = None
    slideshow_music: Optional[bool] = None
    slideshow_volume: Optional[int] = None
    slideshow_loop: Optional[bool] = None
    browse_hidden_paths: Optional[list[str]] = None


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
    cover_index: Optional[int] = None
    slideshow_defaults: Optional[SlideshowDefaults] = None
    timezone_offset: int = 0

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
