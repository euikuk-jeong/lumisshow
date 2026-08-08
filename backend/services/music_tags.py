"""음악 파일 임베디드 메타데이터(제목/아티스트/앨범/커버 이미지) 읽기.

mutagen으로 파일 헤더의 태그만 읽는다 — 태그가 없거나 파싱 실패해도
예외를 던지지 않고 빈 값으로 폴백한다(호출자는 파일명 등으로 대체 표시)."""

import logging
from typing import NamedTuple, Optional

from mutagen import File as MutagenFile

_logger = logging.getLogger(__name__)


class MusicTagInfo(NamedTuple):
    title: Optional[str]
    artist: Optional[str]
    album: Optional[str]
    has_cover: bool


_EMPTY = MusicTagInfo(title=None, artist=None, album=None, has_cover=False)


def _id3_text(tags, frame_id: str) -> Optional[str]:
    frame = tags.get(frame_id)
    if frame is None:
        return None
    value = str(frame).strip()
    return value or None


def _vorbis_text(tags, key: str) -> Optional[str]:
    values = tags.get(key)
    if not values:
        return None
    value = str(values[0]).strip()
    return value or None


def _extract_cover(audio, tags) -> Optional[tuple[bytes, str]]:
    pictures = getattr(audio, "pictures", None)  # FLAC
    if pictures:
        pic = pictures[0]
        return pic.data, pic.mime or "image/jpeg"

    if tags is None:
        return None

    getall = getattr(tags, "getall", None)  # ID3 (MP3, WAV)
    if getall:
        apics = getall("APIC")
        if apics:
            return apics[0].data, apics[0].mime or "image/jpeg"

    covr = tags.get("covr") if hasattr(tags, "get") else None  # MP4/M4A
    if covr:
        cover = covr[0]
        mime = "image/png" if getattr(cover, "imageformat", None) == 14 else "image/jpeg"
        return bytes(cover), mime

    return None


def read_music_tags(abs_path: str) -> MusicTagInfo:
    """제목/아티스트/앨범/커버 유무를 파일 1회 열람으로 함께 읽는다 — 텍스트
    태그는 ID3(MP3/WAV)와 Vorbis Comment(FLAC/OGG/Opus)를 지원, 커버는
    FLAC/MP4까지 폭넓게 인식(추출 비용이 같아 굳이 좁힐 이유가 없음)."""
    try:
        audio = MutagenFile(abs_path)
    except Exception:
        _logger.exception("음악 태그 읽기 실패: %s", abs_path)
        return _EMPTY
    if audio is None:
        return _EMPTY

    tags = audio.tags
    title = artist = album = None
    getall = getattr(tags, "getall", None) if tags is not None else None
    if getall:  # ID3 (MP3, WAV)
        title = _id3_text(tags, "TIT2")
        artist = _id3_text(tags, "TPE1")
        album = _id3_text(tags, "TALB")
    elif tags is not None and hasattr(tags, "get"):  # Vorbis Comment (FLAC, OGG, Opus)
        title = _vorbis_text(tags, "title")
        artist = _vorbis_text(tags, "artist")
        album = _vorbis_text(tags, "album")

    return MusicTagInfo(
        title=title,
        artist=artist,
        album=album,
        has_cover=_extract_cover(audio, tags) is not None,
    )


def read_cover_image(abs_path: str) -> Optional[tuple[bytes, str]]:
    """임베디드 커버 이미지를 (bytes, mime_type)으로 반환. 없으면 None."""
    try:
        audio = MutagenFile(abs_path)
    except Exception:
        _logger.exception("커버 이미지 읽기 실패: %s", abs_path)
        return None
    if audio is None:
        return None
    return _extract_cover(audio, audio.tags)
