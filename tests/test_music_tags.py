import shutil
from pathlib import Path

from mutagen.flac import FLAC, Picture
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


def _make_minimal_flac(path: str) -> None:
    """STREAMINFO 블록 하나만 있는 최소 FLAC 컨테이너 생성(오디오 프레임 없음).
    태그 읽기 테스트는 메타데이터 블록만 있으면 충분하고, 실제 오디오 인코더가 없어
    프레임 데이터까지 만들 수 없다."""
    min_block = max_block = 4096
    bits = (
        format(min_block, "016b")
        + format(max_block, "016b")
        + format(0, "024b")  # min frame size
        + format(0, "024b")  # max frame size
        + format(44100, "020b")  # sample rate
        + format(1, "03b")  # channels - 1 (2ch)
        + format(15, "05b")  # bits per sample - 1 (16bit)
        + format(0, "036b")  # total samples
    )
    streaminfo = int(bits, 2).to_bytes(18, "big") + b"\x00" * 16  # + MD5
    header = bytes([0x80]) + len(streaminfo).to_bytes(3, "big")  # last-block=1, type=0
    with open(path, "wb") as f:
        f.write(b"fLaC" + header + streaminfo)


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


def test_read_music_tags_reads_vorbis_comment_and_flac_picture(tmp_path):
    path = str(tmp_path / "sample.flac")
    _make_minimal_flac(path)

    audio = FLAC(path)
    audio.add_tags()
    audio["title"] = ["FLAC Title"]
    audio["artist"] = ["FLAC Artist"]
    audio["album"] = ["FLAC Album"]

    picture = Picture()
    picture.data = b"\xff\xd8\xff\xd9fakejpeg"
    picture.mime = "image/jpeg"
    picture.type = 3
    audio.add_picture(picture)
    audio.save()

    info = read_music_tags(path)
    assert info.title == "FLAC Title"
    assert info.artist == "FLAC Artist"
    assert info.album == "FLAC Album"
    assert info.has_cover is True

    cover = read_cover_image(path)
    assert cover is not None
    data, mime = cover
    assert data == b"\xff\xd8\xff\xd9fakejpeg"
    assert mime == "image/jpeg"


def test_read_music_tags_flac_no_tags_falls_back_to_empty(tmp_path):
    path = str(tmp_path / "untagged.flac")
    _make_minimal_flac(path)
    info = read_music_tags(path)
    assert info == (None, None, None, False)


def test_read_music_tags_reads_uppercase_vorbis_keys(tmp_path):
    """대다수 태거가 관례적으로 대문자 키(TITLE/ARTIST/ALBUM)를 쓴다 —
    VCommentDict가 조회 시 대소문자를 구분하지 않는지 확인."""
    path = str(tmp_path / "uppercase.flac")
    _make_minimal_flac(path)

    audio = FLAC(path)
    audio.add_tags()
    audio["TITLE"] = ["Upper Title"]
    audio["ARTIST"] = ["Upper Artist"]
    audio["ALBUM"] = ["Upper Album"]
    audio.save()

    info = read_music_tags(path)
    assert info.title == "Upper Title"
    assert info.artist == "Upper Artist"
    assert info.album == "Upper Album"
