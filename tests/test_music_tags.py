import shutil
from pathlib import Path

from mutagen.id3 import ID3, APIC

from backend.services.music_tags import read_cover_image, read_music_tags

_BUNDLED_SAMPLE = (
    Path(__file__).resolve().parent.parent
    / "frontend" / "assets" / "music" / "bundled" / "paulyudin-emotional-emotional-music-573976.mp3"
)


def _copy_sample(tmp_path, name="sample.mp3") -> str:
    """번들 mp3(제목/아티스트/앨범/커버 이미지 ID3 태그 포함) 사본 경로 반환."""
    dest = tmp_path / name
    shutil.copy(_BUNDLED_SAMPLE, dest)
    return str(dest)


def _strip_cover(path: str) -> None:
    tags = ID3(path)
    tags.delall("APIC")
    tags.save(path)


def test_read_music_tags_reads_embedded_id3_and_cover(tmp_path):
    path = _copy_sample(tmp_path)
    info = read_music_tags(path)
    assert info.title == "Emotional"
    assert info.artist == "PaulYudin"
    assert info.album == "Pixabay Music"
    assert info.has_cover is True


def test_read_cover_image_returns_embedded_bytes(tmp_path):
    path = _copy_sample(tmp_path)
    cover = read_cover_image(path)
    assert cover is not None
    data, mime = cover
    assert len(data) > 0
    assert mime == "image/jpeg"


def test_read_cover_image_none_when_no_apic_frame(tmp_path):
    path = _copy_sample(tmp_path)
    _strip_cover(path)
    assert read_cover_image(path) is None
    assert read_music_tags(path).has_cover is False


def test_read_music_tags_and_cover_when_apic_frame_present(tmp_path):
    path = _copy_sample(tmp_path)
    _strip_cover(path)
    tags = ID3(path)
    tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=b"\xff\xd8\xff\xd9fakejpeg"))
    tags.save(path)

    info = read_music_tags(path)
    assert info.has_cover is True

    cover = read_cover_image(path)
    assert cover is not None
    data, mime = cover
    assert data == b"\xff\xd8\xff\xd9fakejpeg"
    assert mime == "image/jpeg"


def test_read_music_tags_no_tags_falls_back_to_empty(tmp_path):
    path = tmp_path / "untagged.mp3"
    path.write_bytes(b"not a real mp3 file")
    info = read_music_tags(str(path))
    assert info == (None, None, None, False)


def test_read_cover_image_missing_file_returns_none(tmp_path):
    assert read_cover_image(str(tmp_path / "does-not-exist.mp3")) is None


def test_read_music_tags_missing_file_returns_empty(tmp_path):
    info = read_music_tags(str(tmp_path / "does-not-exist.mp3"))
    assert info == (None, None, None, False)
