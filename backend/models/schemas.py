import json
import os
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


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

class AlbumDuplicateRequest(BaseModel):
    name: str

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
    ui_theme: Optional[str] = None

class AlbumPhotoResponse(BaseModel):
    id: int
    album_id: int
    file_path: str
    sort_order: int
    added_at: datetime
    taken_at: Optional[datetime] = None

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
    ui_theme: Optional[str] = None

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
    ui_theme: str = "dark"

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
    ui_theme: Optional[str] = None


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
    ui_theme: str = "dark"

class SharePhotoItem(BaseModel):
    id: int
    url: str
    thumb_small_url: str
    thumb_medium_url: str
    filename: Optional[str]
    file_path: Optional[str] = None  # Admin 응답 전용 — 공유 링크에는 노출하지 않음
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
    page: int = 1
    snapshot: Optional[str] = None  # 인물 사진 페이지네이션 스냅샷 토큰 (admin_people.py 전용)


_EXIF_META_FIELDS = (
    "taken_at", "width", "height", "make", "camera", "software",
    "shutter", "aperture", "iso", "focal_length", "shoot_mode",
    "flash", "metering", "exposure_mode",
)


def build_share_photo_item(
    id: int, file_path: str, url: str,
    thumb_small_url: str, thumb_medium_url: str, meta: dict,
    include_file_path: bool = False,
) -> SharePhotoItem:
    """EXIF meta dict → SharePhotoItem. share.py·admin_people.py 공용 빌더.

    include_file_path는 Admin 응답에서만 True — 공유 링크에 경로 구조 노출 방지."""
    return SharePhotoItem(
        id=id,
        url=url,
        thumb_small_url=thumb_small_url,
        thumb_medium_url=thumb_medium_url,
        filename=os.path.basename(file_path),
        file_path=file_path if include_file_path else None,
        **{k: meta.get(k) for k in _EXIF_META_FIELDS},
    )


def build_slideshow_defaults(overrides: dict, sv: dict) -> dict:
    """오버라이드(앨범 행 필드, 또는 person 슬라이드쇼처럼 일부 키만 지정된 dict)와
    전역 설정(sv)을 병합해 slideshow_defaults 응답 형태를 만든다. overrides에 키가
    없거나 값이 None이면 sv로 폴백 — share.py get_album()과 admin_people.py 인물
    슬라이드쇼가 공유하는 단일 규칙."""
    music = overrides.get("music")
    loop = overrides.get("loop")
    return {
        "interval": overrides.get("interval") or sv["slideshow_interval"],
        "order":    overrides.get("order")    or sv["slideshow_order"],
        "effect":   overrides.get("effect")   or sv["slideshow_effect"],
        "music":    bool(music) if music is not None else sv["slideshow_music"],
        "volume":   overrides.get("volume") if overrides.get("volume") is not None else sv["slideshow_volume"],
        "loop":     bool(loop) if loop is not None else sv["slideshow_loop"],
    }


# ── People (Phase 2 AI) ───────────────────────────────────────────────────────

class PersonCreate(BaseModel):
    name: str

class FaceLabelSet(BaseModel):
    person_id: Optional[int] = None   # None = 등록 인물 아님(무시)

class BatchFaceLabel(BaseModel):
    face_ids: list[int] = Field(max_length=5000)
    person_id: Optional[int] = None

class BatchFaceUnlabel(BaseModel):
    face_ids: list[int] = Field(max_length=5000)

class ConfirmByScore(BaseModel):
    min_score: float = Field(ge=0.0, le=1.0)

class JobCreate(BaseModel):
    type: str                          # scan | rematch

class AiSettingsUpdate(BaseModel):
    scan_hour: int = Field(ge=0, le=23)  # 야간 자동 스캔 시각 (로컬 TZ)
