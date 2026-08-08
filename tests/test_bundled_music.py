from pathlib import Path

from backend.services import bundled_music


def _make_source(tmp_path, monkeypatch, files):
    source_dir = tmp_path / "source_bundled"
    source_dir.mkdir()
    for name, content in files.items():
        (source_dir / name).write_bytes(content)
    monkeypatch.setattr(bundled_music, "_BUNDLED_SOURCE_DIR", source_dir)
    return source_dir


def test_sync_copies_bundled_files(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    _make_source(tmp_path, monkeypatch, {"a.mp3": b"aaa", "b.mp3": b"bbb"})

    bundled_music.sync_bundled_music()

    target_dir = tmp_path / "data" / "music" / "bundled"
    assert (target_dir / "a.mp3").read_bytes() == b"aaa"
    assert (target_dir / "b.mp3").read_bytes() == b"bbb"


def test_sync_prunes_stale_files_no_longer_bundled(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    _make_source(tmp_path, monkeypatch, {"a.mp3": b"aaa"})

    target_dir = tmp_path / "data" / "music" / "bundled"
    target_dir.mkdir(parents=True)
    (target_dir / "old-track.mp3").write_bytes(b"old")

    bundled_music.sync_bundled_music()

    assert not (target_dir / "old-track.mp3").exists()
    assert (target_dir / "a.mp3").read_bytes() == b"aaa"


def test_sync_does_not_touch_user_uploaded_files_outside_bundled_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    _make_source(tmp_path, monkeypatch, {"a.mp3": b"aaa"})

    music_dir = tmp_path / "data" / "music"
    music_dir.mkdir(parents=True)
    (music_dir / "user-uploaded.mp3").write_bytes(b"user")

    bundled_music.sync_bundled_music()

    assert (music_dir / "user-uploaded.mp3").read_bytes() == b"user"


def test_sync_is_noop_when_source_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(bundled_music, "_BUNDLED_SOURCE_DIR", tmp_path / "does-not-exist")

    bundled_music.sync_bundled_music()

    assert not (tmp_path / "data" / "music" / "bundled").exists()
