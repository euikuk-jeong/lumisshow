"""ai_worker 단위 테스트 — 모델(insightface) 설치 없이 실행 가능한 범위:
db 스키마, 증분 스캐너, cosine 매처, 라벨링 도구."""

import logging
import os
import time

import numpy as np
import pytest

from ai_worker import db, geocoder, matcher, pipeline, scanner, tag_vocab, tagger


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PHOTO_ROOT", str(tmp_path / "photos"))
    (tmp_path / "photos").mkdir(parents=True, exist_ok=True)
    connection = db.connect()
    yield connection
    connection.close()


def _insert_face(conn, photo_path: str, vec: np.ndarray) -> int:
    cur = conn.execute(
        "INSERT INTO faces (photo_path, bbox, det_score, embedding) VALUES (?, ?, ?, ?)",
        (photo_path, "[0,0,10,10]", 0.9, matcher.embedding_to_blob(vec)),
    )
    return cur.lastrowid


def _unit_vec(axis: int) -> np.ndarray:
    vec = np.zeros(matcher.EMBEDDING_DIM, dtype=np.float32)
    vec[axis] = 1.0
    return vec


# ── db ────────────────────────────────────────────────────────────────


def test_db_creates_tables(conn):
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"photos_analyzed", "faces", "face_matches", "persons", "face_labels",
            "jobs", "ignored_review_candidates", "pending_path_repairs",
            "pending_orphan_cleanups", "photo_tags", "photo_locations",
            "photo_embeddings"} <= tables


def test_db_creates_person_indexes(conn):
    """list_people 등 person_id 조회용 인덱스가 생성돼야 한다."""
    indexes = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
    }
    assert {
        "idx_faces_photo", "idx_face_matches_person", "idx_face_labels_person", "idx_persons_name",
    } <= indexes


def test_db_wal_mode(conn):
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_face_delete_cascades_to_labels_and_matches(conn):
    face_id = _insert_face(conn, "a.jpg", _unit_vec(0))
    conn.execute("INSERT INTO persons (name) VALUES ('테스트')")
    conn.execute("INSERT INTO face_labels (face_id, person_id) VALUES (?, 1)", (face_id,))
    conn.execute(
        "INSERT INTO face_matches (face_id, person_id, score) VALUES (?, 1, 0.9)",
        (face_id,),
    )
    conn.execute("DELETE FROM faces WHERE id = ?", (face_id,))
    assert conn.execute("SELECT COUNT(*) FROM face_labels").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM face_matches").fetchone()[0] == 0


# ── scanner ───────────────────────────────────────────────────────────


def _make_photo(root, rel: str) -> str:
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fp:
        fp.write(b"fake")
    return path


def test_scanner_finds_new_photos(conn, tmp_path):
    root = str(tmp_path / "photos")
    _make_photo(root, "2024/a.jpg")
    _make_photo(root, "2024/b.PNG")          # 대문자 확장자도 포함
    _make_photo(root, "2024/note.txt")       # 이미지 아님 → 제외
    _make_photo(root, "@eaDir/thumb.jpg")    # Synology 메타 폴더 → 제외

    pending = scanner.pending_photos(conn, root)
    assert sorted(p for p, _ in pending) == ["2024/a.jpg", "2024/b.PNG"]


def test_scanner_skips_analyzed_and_detects_mtime_change(conn, tmp_path):
    root = str(tmp_path / "photos")
    path = _make_photo(root, "a.jpg")
    mtime = os.path.getmtime(path)
    conn.execute(
        "INSERT INTO photos_analyzed (path, mtime, face_count) VALUES ('a.jpg', ?, 0)",
        (mtime,),
    )
    assert scanner.pending_photos(conn, root) == []

    # mtime 변경 → 재분석 대상
    os.utime(path, (time.time() + 100, time.time() + 100))
    assert [p for p, _ in scanner.pending_photos(conn, root)] == ["a.jpg"]


def test_scanner_retries_stale_error_status_even_without_mtime_change(conn, tmp_path):
    """일시적 오류 등으로 status='error'가 된 사진은 파일이 안 바뀌어(mtime 그대로)도
    _ERROR_RETRY_DAYS일 넘게 지나면 다시 분석 대상에 포함돼야 한다 — 그렇지 않으면
    영구 방치된다."""
    root = str(tmp_path / "photos")
    path = _make_photo(root, "a.jpg")
    mtime = os.path.getmtime(path)
    conn.execute(
        "INSERT INTO photos_analyzed (path, mtime, face_count, status, analyzed_at) "
        "VALUES ('a.jpg', ?, 0, 'error', datetime('now', '-30 days'))",
        (mtime,),
    )
    conn.commit()
    assert [p for p, _ in scanner.pending_photos(conn, root)] == ["a.jpg"]


def test_scanner_does_not_retry_recent_error_status(conn, tmp_path):
    """방금 실패한 사진(analyzed_at이 최근)은 재시도 창 안이라 매 스캔 재시도하지
    않는다 — 그래야 지속 실패 파일이 매일 밤 모델 로딩·Discord 알림을 유발하지 않는다."""
    root = str(tmp_path / "photos")
    path = _make_photo(root, "a.jpg")
    mtime = os.path.getmtime(path)
    conn.execute(
        "INSERT INTO photos_analyzed (path, mtime, face_count, status) "
        "VALUES ('a.jpg', ?, 0, 'error')",
        (mtime,),
    )
    conn.commit()
    assert scanner.pending_photos(conn, root) == []


def test_scanner_queues_renamed_photo_proposal_without_applying(conn, tmp_path):
    root = str(tmp_path / "photos")
    old_path = _make_photo(root, "2024/a.jpg")
    mtime = os.path.getmtime(old_path)
    conn.execute(
        "INSERT INTO photos_analyzed (path, mtime, face_count) VALUES ('2024/a.jpg', ?, 1)",
        (mtime,),
    )
    face_id = _insert_face(conn, "2024/a.jpg", _unit_vec(0))
    conn.execute("INSERT INTO persons (name) VALUES ('테스트')")
    conn.execute("INSERT INTO face_labels (face_id, person_id) VALUES (?, 1)", (face_id,))
    conn.commit()

    os.makedirs(os.path.join(root, "2025"), exist_ok=True)
    os.rename(old_path, os.path.join(root, "2025", "a.jpg"))  # 폴더 이동, 파일명(basename)은 유지

    pending = scanner.pending_photos(conn, root)
    assert pending == []  # 승인 대기 중인 new_path는 재분석 대상 아님

    # 승인 전이므로 photos_analyzed/faces는 아직 old_path 그대로 — 즉시 UPDATE 안 함
    row = conn.execute("SELECT path FROM photos_analyzed").fetchone()
    assert row["path"] == "2024/a.jpg"
    face_row = conn.execute("SELECT id, photo_path FROM faces").fetchone()
    assert face_row["id"] == face_id
    assert face_row["photo_path"] == "2024/a.jpg"

    proposal = conn.execute(
        "SELECT old_path, new_path, source, status FROM pending_path_repairs"
    ).fetchone()
    assert proposal["old_path"] == "2024/a.jpg"
    assert proposal["new_path"] == "2025/a.jpg"
    assert proposal["source"] == "scan"
    assert proposal["status"] == "pending"


def test_scanner_rescan_does_not_duplicate_proposal(conn, tmp_path):
    root = str(tmp_path / "photos")
    old_path = _make_photo(root, "2024/a.jpg")
    mtime = os.path.getmtime(old_path)
    conn.execute(
        "INSERT INTO photos_analyzed (path, mtime, face_count) VALUES ('2024/a.jpg', ?, 0)",
        (mtime,),
    )
    conn.commit()
    os.makedirs(os.path.join(root, "2025"), exist_ok=True)
    os.rename(old_path, os.path.join(root, "2025", "a.jpg"))

    scanner.pending_photos(conn, root)
    scanner.pending_photos(conn, root)  # 재스캔해도 제안이 중복으로 쌓이지 않아야 함

    assert conn.execute("SELECT COUNT(*) FROM pending_path_repairs").fetchone()[0] == 1


def test_scanner_ambiguous_rename_not_proposed(conn, tmp_path):
    root = str(tmp_path / "photos")
    _make_photo(root, "new1/a.jpg")
    _make_photo(root, "new2/a.jpg")
    conn.execute(
        "INSERT INTO photos_analyzed (path, mtime, face_count) VALUES ('old/a.jpg', 123.0, 0)"
    )
    conn.commit()

    pending = scanner.pending_photos(conn, root)
    assert sorted(p for p, _ in pending) == ["new1/a.jpg", "new2/a.jpg"]
    # 후보가 2개라 제안조차 쌓이지 않고 old 행이 그대로 남아 orphan 유지
    assert conn.execute(
        "SELECT COUNT(*) FROM photos_analyzed WHERE path = 'old/a.jpg'"
    ).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM pending_path_repairs").fetchone()[0] == 0


def test_scanner_queues_orphan_cleanup_when_no_rename_candidate(conn, tmp_path):
    root = str(tmp_path / "photos")
    still_here = _make_photo(root, "still/here.jpg")  # walk 결과가 비어 abort되지 않도록
    conn.execute(
        "INSERT INTO photos_analyzed (path, mtime, face_count) VALUES ('still/here.jpg', ?, 0)",
        (os.path.getmtime(still_here),),
    )
    conn.execute(
        "INSERT INTO photos_analyzed (path, mtime, face_count) VALUES ('gone/a.jpg', 123.0, 0)"
    )
    conn.commit()

    pending = scanner.pending_photos(conn, root)
    assert pending == []  # 삭제된 파일은 분석 대상이 아니고, still/here.jpg는 이미 분석됨

    proposal = conn.execute(
        "SELECT path, source, status FROM pending_orphan_cleanups"
    ).fetchone()
    assert proposal["path"] == "gone/a.jpg"
    assert proposal["source"] == "scan"
    assert proposal["status"] == "pending"

    # rename 제안 쪽엔 쌓이지 않아야 한다
    assert conn.execute("SELECT COUNT(*) FROM pending_path_repairs").fetchone()[0] == 0


def test_scanner_ambiguous_rename_not_queued_as_orphan(conn, tmp_path):
    """rename 후보가 2개 이상(ambiguous)인 경로는 orphan 삭제 제안에도 안 쌓인다."""
    root = str(tmp_path / "photos")
    _make_photo(root, "new1/a.jpg")
    _make_photo(root, "new2/a.jpg")
    conn.execute(
        "INSERT INTO photos_analyzed (path, mtime, face_count) VALUES ('old/a.jpg', 123.0, 0)"
    )
    conn.commit()

    scanner.pending_photos(conn, root)
    assert conn.execute("SELECT COUNT(*) FROM pending_orphan_cleanups").fetchone()[0] == 0


def test_scanner_rescan_does_not_duplicate_orphan_proposal(conn, tmp_path):
    root = str(tmp_path / "photos")
    still_here = _make_photo(root, "still/here.jpg")  # walk 결과가 비어 abort되지 않도록
    conn.execute(
        "INSERT INTO photos_analyzed (path, mtime, face_count) VALUES ('still/here.jpg', ?, 0)",
        (os.path.getmtime(still_here),),
    )
    conn.execute(
        "INSERT INTO photos_analyzed (path, mtime, face_count) VALUES ('gone/a.jpg', 123.0, 0)"
    )
    conn.commit()

    scanner.pending_photos(conn, root)
    scanner.pending_photos(conn, root)

    assert conn.execute("SELECT COUNT(*) FROM pending_orphan_cleanups").fetchone()[0] == 1


def test_scanner_aborts_when_root_unreachable(conn, tmp_path):
    root = str(tmp_path / "photos")
    conn.execute(
        "INSERT INTO photos_analyzed (path, mtime, face_count) VALUES ('a.jpg', 123.0, 0)"
    )
    conn.commit()

    # root는 존재하지만 비어 있음(마운트 해제 등으로 walk 결과가 없는 상황 재현)
    assert scanner.pending_photos(conn, root) == []
    assert conn.execute(
        "SELECT COUNT(*) FROM photos_analyzed"
    ).fetchone()[0] == 1  # 오인 삭제/변경 없이 그대로 유지


# ── 폴더명 태깅 (Kiwi) ───────────────────────────────────────────────


class _FakeToken:
    def __init__(self, form: str, tag: str) -> None:
        self.form = form
        self.tag = tag


class _CountingKiwi:
    """kiwipiepy 설치 없이 scanner의 폴더 단위 캐싱·필터링 로직만 검증하기 위한 스텁."""

    def __init__(self, mapping: dict[str, list[_FakeToken]]) -> None:
        self._mapping = mapping
        self.calls = 0

    def tokenize(self, text: str) -> list[_FakeToken]:
        self.calls += 1
        return self._mapping.get(text, [])


def test_extract_folder_nouns_filters_short_and_dedups(monkeypatch):
    fake = _CountingKiwi({
        "20250511_서울대공원캠핑장_f": [
            _FakeToken("서울대공원", "NNP"), _FakeToken("캠핑", "NNG"), _FakeToken("장", "NNG"),
        ],
        "부산부산": [_FakeToken("부산", "NNP"), _FakeToken("부산", "NNP")],
        "IMG_2024": [_FakeToken("IMG", "SL"), _FakeToken("2024", "SN")],
    })
    monkeypatch.setattr(scanner, "_get_kiwi", lambda: fake)

    assert scanner.extract_folder_nouns("20250511_서울대공원캠핑장_f") == ["서울대공원", "캠핑"]
    assert scanner.extract_folder_nouns("부산부산") == ["부산"]  # 중복 제거
    assert scanner.extract_folder_nouns("IMG_2024") == []  # 명사 없음(SL/SN만)


def test_tag_paths_from_folder_names_covers_untagged_photos_and_caches_per_folder(conn, monkeypatch):
    fake = _CountingKiwi({"캠핑장": [_FakeToken("캠핑", "NNG")]})
    monkeypatch.setattr(scanner, "_get_kiwi", lambda: fake)

    conn.execute("INSERT INTO photos_analyzed (path, mtime) VALUES ('2024/캠핑장/a.jpg', 0)")
    conn.execute("INSERT INTO photos_analyzed (path, mtime) VALUES ('2024/캠핑장/b.jpg', 0)")
    conn.commit()

    tagged = scanner.tag_paths_from_folder_names(conn)
    assert tagged == 2
    assert fake.calls == 1  # 같은 폴더는 1회만 Kiwi 호출(폴더 단위 캐싱)

    rows = conn.execute(
        "SELECT photo_path FROM photo_tags WHERE tag = '캠핑' AND source = 'path'"
    ).fetchall()
    assert {r["photo_path"] for r in rows} == {"2024/캠핑장/a.jpg", "2024/캠핑장/b.jpg"}

    # 이미 path 태그가 있는 사진은 커버리지 대상에서 빠진다 — 재실행해도 재호출 없음
    assert scanner.tag_paths_from_folder_names(conn) == 0
    assert fake.calls == 1


def test_tag_paths_from_folder_names_marks_zero_noun_folders_done_without_retry(conn, monkeypatch):
    """순수 영문/숫자 폴더처럼 명사가 하나도 안 나오면 태그 행은 안 생기지만
    path_tag_done은 시도 여부만 보고 1로 표시되어 다음 스캔부터 재시도하지 않는다
    (2026-08-04: photo_tags 행 존재 여부 기반 커버리지에서 path_tag_done 플래그
    기반으로 전환 — 이전에는 이런 사진이 매 스캔 재시도되며 path_tagged 건수를
    끝없이 부풀렸다)."""
    fake = _CountingKiwi({"IMG_2024": []})
    monkeypatch.setattr(scanner, "_get_kiwi", lambda: fake)
    conn.execute("INSERT INTO photos_analyzed (path, mtime) VALUES ('2024/IMG_2024/a.jpg', 0)")
    conn.commit()

    assert scanner.tag_paths_from_folder_names(conn) == 0
    assert conn.execute("SELECT COUNT(*) FROM photo_tags").fetchone()[0] == 0
    assert conn.execute(
        "SELECT path_tag_done FROM photos_analyzed WHERE path = '2024/IMG_2024/a.jpg'"
    ).fetchone()[0] == 1

    assert scanner.tag_paths_from_folder_names(conn) == 0
    assert fake.calls == 1  # 재시도 없음 — Kiwi 다시 호출되지 않아야 함


def test_tag_paths_from_folder_names_no_pending_returns_zero(conn):
    assert scanner.tag_paths_from_folder_names(conn) == 0


def test_run_path_tag_reset_recomputes_already_done_photos(conn, monkeypatch):
    """Kiwi 사전/로직이 바뀌어 기존 태그가 stale해진 상황을 재현 — 이미
    path_tag_done=1인 사진도 run_path_tag_reset()이 지우고 다시 태깅해야 한다."""
    from ai_worker import main

    fake = _CountingKiwi({"캠핑장": [_FakeToken("캠핑장", "NNP")]})
    monkeypatch.setattr(scanner, "_get_kiwi", lambda: fake)

    conn.execute("INSERT INTO photos_analyzed (path, mtime) VALUES ('2024/캠핑장/a.jpg', 0)")
    conn.execute(
        "INSERT INTO photo_tags (photo_path, tag, source) VALUES ('2024/캠핑장/a.jpg', '캠핑', 'path')"
    )
    conn.execute(
        "UPDATE photos_analyzed SET path_tag_done = 1 WHERE path = '2024/캠핑장/a.jpg'"
    )
    conn.commit()

    summary = main.run_path_tag_reset()
    assert summary["path_tagged"] == 1

    rows = {
        r["tag"] for r in conn.execute(
            "SELECT tag FROM photo_tags WHERE photo_path = '2024/캠핑장/a.jpg' AND source = 'path'"
        ).fetchall()
    }
    assert rows == {"캠핑장"}  # 옛 태그('캠핑')는 지워지고 새 어휘 결과만 남는다
    assert conn.execute(
        "SELECT path_tag_done FROM photos_analyzed WHERE path = '2024/캠핑장/a.jpg'"
    ).fetchone()[0] == 1


def test_run_path_tag_reset_skips_when_path_disabled(conn, monkeypatch):
    from ai_worker import main

    def _boom():
        raise AssertionError("path_enabled=0이면 폴더명 태깅을 호출하면 안 됨")

    monkeypatch.setattr(scanner, "tag_paths_from_folder_names", lambda conn: _boom())
    conn.execute("INSERT INTO ai_settings (key, value) VALUES ('path_enabled', '0')")
    conn.execute("INSERT INTO photos_analyzed (path, mtime) VALUES ('2024/a.jpg', 0)")
    conn.commit()

    summary = main.run_path_tag_reset()
    assert summary == {"path_tagged": 0, "elapsed": 0.0}


# ── GPS 위치 태깅 (geocoder) ─────────────────────────────────────────


class _FakeExif(dict):
    def __init__(self, base: dict, gps_ifd: dict) -> None:
        super().__init__(base)
        self._gps_ifd = gps_ifd

    def get_ifd(self, tag):
        return self._gps_ifd


class _FakeImg:
    def __init__(self, base: dict, gps_ifd: dict) -> None:
        self._exif = _FakeExif(base, gps_ifd)

    def getexif(self):
        return self._exif


def test_extract_gps_none_without_exif():
    assert pipeline._extract_gps(_FakeImg({}, {})) is None


def test_extract_gps_none_without_gps_ifd():
    assert pipeline._extract_gps(_FakeImg({0x0112: 1}, {})) is None


def test_extract_gps_parses_north_east_as_positive():
    img = _FakeImg({0x0112: 1}, {1: "N", 2: (37.0, 33.0, 0.0), 3: "E", 4: (127.0, 0.0, 0.0)})
    lat, lon = pipeline._extract_gps(img)
    assert lat == pytest.approx(37.55, abs=0.01)
    assert lon == pytest.approx(127.0, abs=0.01)


def test_extract_gps_parses_south_west_as_negative():
    img = _FakeImg({0x0112: 1}, {1: "S", 2: (37.0, 0.0, 0.0), 3: "W", 4: (127.0, 0.0, 0.0)})
    lat, lon = pipeline._extract_gps(img)
    assert lat < 0
    assert lon < 0


def test_extract_gps_none_on_malformed_values():
    img = _FakeImg({0x0112: 1}, {1: "N", 2: (37.0,), 3: "E", 4: (127.0, 0.0, 0.0)})
    assert pipeline._extract_gps(img) is None


def test_extract_gps_none_on_nan_from_broken_fraction():
    """Pillow IFDRational은 EXIF 분수 필드의 분모가 0이면 예외 없이 nan을 반환한다
    (깨진 GPS 태그) — 그대로 넘기면 geocoder의 cKDTree.query가 크래시한다."""
    img = _FakeImg(
        {0x0112: 1}, {1: "N", 2: (37.0, 33.0, float("nan")), 3: "E", 4: (127.0, 0.0, 0.0)}
    )
    assert pipeline._extract_gps(img) is None


def test_reverse_geocode_maps_country_code_to_korean(monkeypatch):
    class _FakeGeocoder:
        def query(self, coords):
            return [{"name": "Seoul", "cc": "KR"}]

    monkeypatch.setattr(geocoder, "_get_geocoder", lambda: _FakeGeocoder())
    city, country = geocoder.reverse_geocode(37.5665, 126.978)
    assert city == "서울"  # _CITY_NAMES_KO 매핑 대상
    assert country == "대한민국"


def test_reverse_geocode_falls_back_to_raw_code_when_unmapped(monkeypatch):
    class _FakeGeocoder:
        def query(self, coords):
            return [{"name": "Nowhere", "cc": "ZZ"}]

    monkeypatch.setattr(geocoder, "_get_geocoder", lambda: _FakeGeocoder())
    city, country = geocoder.reverse_geocode(0.0, 0.0)
    assert city == "Nowhere"
    assert country == "ZZ"


def test_reverse_geocode_falls_back_to_raw_city_when_unmapped(monkeypatch):
    """국가는 매핑되지만((country, city) 조합이 딕셔너리에 없는) 도시명은 로마자
    그대로 폴백해야 한다 — 큐레이션 안 된 지명이 오역 없이 노출되는 게 목표."""
    class _FakeGeocoder:
        def query(self, coords):
            return [{"name": "SomeUnmappedTown", "cc": "KR"}]

    monkeypatch.setattr(geocoder, "_get_geocoder", lambda: _FakeGeocoder())
    city, country = geocoder.reverse_geocode(0.0, 0.0)
    assert city == "SomeUnmappedTown"
    assert country == "대한민국"


def test_retranslate_cities_updates_existing_rows_and_resyncs_tags(conn):
    conn.execute(
        "INSERT INTO photo_locations (photo_path, city, country) VALUES (?, ?, ?)",
        ("2024/a.jpg", "Kwangmyong", "대한민국"),
    )
    conn.execute(
        "INSERT INTO photo_tags (photo_path, tag, source) VALUES ('2024/a.jpg', 'Kwangmyong', 'location')"
    )
    conn.commit()

    changed = geocoder.retranslate_cities(conn)
    assert changed == 1

    row = conn.execute(
        "SELECT city FROM photo_locations WHERE photo_path = '2024/a.jpg'"
    ).fetchone()
    assert row["city"] == "광명"
    tags = {
        r["tag"] for r in conn.execute(
            "SELECT tag FROM photo_tags WHERE photo_path = '2024/a.jpg' AND source = 'location'"
        ).fetchall()
    }
    assert tags == {"광명", "대한민국"}  # 옛 로마자 태그는 지워지고 번역된 값만 남는다


def test_retranslate_cities_skips_unmapped_rows(conn):
    conn.execute(
        "INSERT INTO photo_locations (photo_path, city, country) VALUES (?, ?, ?)",
        ("2024/a.jpg", "SomeUnmappedTown", "대한민국"),
    )
    conn.commit()

    changed = geocoder.retranslate_cities(conn)
    assert changed == 0
    row = conn.execute(
        "SELECT city FROM photo_locations WHERE photo_path = '2024/a.jpg'"
    ).fetchone()
    assert row["city"] == "SomeUnmappedTown"


def test_run_location_tag_reset_translates_and_reports_count(conn):
    from ai_worker import main

    conn.execute(
        "INSERT INTO photo_locations (photo_path, city, country) VALUES (?, ?, ?)",
        ("2024/a.jpg", "Seoul", "대한민국"),
    )
    conn.commit()

    summary = main.run_location_tag_reset()
    assert summary["translated"] == 1
    row = conn.execute(
        "SELECT city FROM photo_locations WHERE photo_path = '2024/a.jpg'"
    ).fetchone()
    assert row["city"] == "서울"


def test_sync_location_tag_creates_city_and_country_rows(conn):
    conn.execute(
        "INSERT INTO photo_locations (photo_path, city, country) VALUES (?, ?, ?)",
        ("2024/a.jpg", "Seoul", "대한민국"),
    )
    geocoder.sync_location_tag(conn, "2024/a.jpg")
    tags = {
        r["tag"] for r in conn.execute(
            "SELECT tag FROM photo_tags WHERE photo_path = ? AND source = 'location'",
            ("2024/a.jpg",),
        )
    }
    assert tags == {"Seoul", "대한민국"}


def test_sync_location_tag_removes_tags_when_location_row_missing(conn):
    conn.execute(
        "INSERT INTO photo_tags (photo_path, tag, source) VALUES ('2024/a.jpg', 'Seoul', 'location')"
    )
    conn.commit()
    geocoder.sync_location_tag(conn, "2024/a.jpg")
    assert conn.execute(
        "SELECT COUNT(*) FROM photo_tags WHERE photo_path = '2024/a.jpg' AND source = 'location'"
    ).fetchone()[0] == 0


def test_pipeline_update_location_upserts_then_clears_on_no_gps(conn, monkeypatch):
    monkeypatch.setattr(geocoder, "reverse_geocode", lambda lat, lon: ("Seoul", "대한민국"))

    pipeline._update_location(conn, "2024/a.jpg", (37.5, 127.0))
    row = conn.execute(
        "SELECT city, country FROM photo_locations WHERE photo_path = '2024/a.jpg'"
    ).fetchone()
    assert (row["city"], row["country"]) == ("Seoul", "대한민국")
    tags = {
        r["tag"] for r in conn.execute(
            "SELECT tag FROM photo_tags WHERE photo_path = '2024/a.jpg' AND source = 'location'"
        )
    }
    assert tags == {"Seoul", "대한민국"}

    # 재분석 시 GPS가 사라진 경우(EXIF 수정 등) — 기존 위치/태그도 함께 정리돼야 한다
    pipeline._update_location(conn, "2024/a.jpg", None)
    assert conn.execute(
        "SELECT COUNT(*) FROM photo_locations WHERE photo_path = '2024/a.jpg'"
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM photo_tags WHERE photo_path = '2024/a.jpg' AND source = 'location'"
    ).fetchone()[0] == 0


def test_pipeline_update_location_swallows_geocode_errors(conn, monkeypatch):
    def _boom(lat, lon):
        raise RuntimeError("offline data missing")

    monkeypatch.setattr(geocoder, "reverse_geocode", _boom)
    pipeline._update_location(conn, "2024/a.jpg", (37.5, 127.0))  # 예외가 밖으로 전파되면 안 됨
    assert conn.execute(
        "SELECT COUNT(*) FROM photo_locations WHERE photo_path = '2024/a.jpg'"
    ).fetchone()[0] == 0


class _StubClipTagger:
    def __init__(self, embed: np.ndarray) -> None:
        self._embed = embed

    def embed_image(self, img) -> np.ndarray:
        return self._embed


def test_analyze_and_store_persists_location_from_stub_pipeline(conn, monkeypatch):
    """pipeline.analyze()가 (faces, img, gps) 3-tuple을 반환하도록 바뀐 계약과
    analyze_and_store의 언패킹·photo_locations/photo_tags/photo_embeddings 기록까지
    실제 함수 경로로 검증(insightface/CLIP 모델 없이 스텁 사용)."""
    from PIL import Image

    monkeypatch.setattr(geocoder, "reverse_geocode", lambda lat, lon: ("Seoul", "대한민국"))
    monkeypatch.setattr(tag_vocab, "TAG_VOCAB", [
        {"prompt": "a photo of camping", "label": "캠핑"},
        {"prompt": "a photo of the sea", "label": "바다"},
    ])

    class _StubPipeline:
        def analyze(self, path):
            return [], Image.new("RGB", (1, 1)), (37.5665, 126.978)

    # "캠핑" 축과 완전히 일치하는 벡터 — threshold(0.5) 이상은 "캠핑"만
    clip_ctx = tagger.ClipTaggingContext(
        tagger=_StubClipTagger(np.array([1.0, 0.0], dtype=np.float32)),
        text_embeds=np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
        threshold=0.5,
    )

    face_count, ok, located, tagged = pipeline.analyze_and_store(
        _StubPipeline(), conn, "2024/a.jpg", 123.0, enrollment={}, threshold=0.45,
        clip_ctx=clip_ctx,
    )
    assert (face_count, ok, located, tagged) == (0, True, True, True)

    row = conn.execute(
        "SELECT status, face_count FROM photos_analyzed WHERE path = '2024/a.jpg'"
    ).fetchone()
    assert (row["status"], row["face_count"]) == ("done", 0)

    loc = conn.execute(
        "SELECT city, country FROM photo_locations WHERE photo_path = '2024/a.jpg'"
    ).fetchone()
    assert (loc["city"], loc["country"]) == ("Seoul", "대한민국")

    tags = {
        r["tag"] for r in conn.execute(
            "SELECT tag FROM photo_tags WHERE photo_path = '2024/a.jpg' AND source = 'location'"
        )
    }
    assert tags == {"Seoul", "대한민국"}

    assert conn.execute(
        "SELECT COUNT(*) FROM photo_embeddings WHERE photo_path = '2024/a.jpg'"
    ).fetchone()[0] == 1
    ai_tags = {
        r["tag"] for r in conn.execute(
            "SELECT tag FROM photo_tags WHERE photo_path = '2024/a.jpg' AND source = 'ai'"
        )
    }
    assert ai_tags == {"캠핑"}  # sim("바다")=0.0 < threshold(0.5)

    # 재분석 시 이번엔 "바다" 축과 일치 — 기존 'ai' 태그(캠핑)는 지워지고 바다로 교체
    clip_ctx.tagger = _StubClipTagger(np.array([0.0, 1.0], dtype=np.float32))
    pipeline.analyze_and_store(
        _StubPipeline(), conn, "2024/a.jpg", 124.0, enrollment={}, threshold=0.45,
        clip_ctx=clip_ctx,
    )
    ai_tags = {
        r["tag"] for r in conn.execute(
            "SELECT tag FROM photo_tags WHERE photo_path = '2024/a.jpg' AND source = 'ai'"
        )
    }
    assert ai_tags == {"바다"}


def test_analyze_and_store_logs_and_records_error_on_analyze_failure(conn, caplog):
    """analyze() 실패 시 status='error'로 기록될 뿐 아니라, 원인(트레이스백)이 로그에
    남아야 admin이 ai.db를 직접 SELECT하지 않고도 원인을 파악할 수 있다."""
    class _BoomPipeline:
        def analyze(self, path):
            raise RuntimeError("decode boom")

    with caplog.at_level(logging.ERROR, logger="ai_worker.pipeline"):
        face_count, ok, located, tagged = pipeline.analyze_and_store(
            _BoomPipeline(), conn, "2024/broken.jpg", 123.0, enrollment={}, threshold=0.45,
        )
    assert (face_count, ok, located, tagged) == (0, False, False, False)

    row = conn.execute(
        "SELECT status FROM photos_analyzed WHERE path = '2024/broken.jpg'"
    ).fetchone()
    assert row["status"] == "error"

    assert any("2024/broken.jpg" in r.message for r in caplog.records)
    assert any(r.exc_info for r in caplog.records)


def _seed_ai_tag(conn, photo_path: str, tag: str = "캠핑") -> None:
    conn.execute(
        "INSERT INTO photo_tags (photo_path, tag, source) VALUES (?, ?, 'ai')",
        (photo_path, tag),
    )
    conn.commit()


def test_analyze_and_store_keeps_stale_ai_tags_on_embed_failure(conn):
    """CLIP 임베딩이 예외를 던져도(모델 손상 등) 얼굴 분석 결과는 그대로 보존돼야
    한다 — best-effort. Kiwi/GPS와 달리 CLIP은 다음 스캔에서 자동으로 다시 채워지지
    않는(coverage 방식이 아닌) 트랙이라, 실패 시 기존 'ai' 태그를 지우면 안 된다
    (지우기만 하고 못 채우면 영구 유실)."""
    from PIL import Image

    _seed_ai_tag(conn, "2024/a.jpg")

    class _StubPipeline:
        def analyze(self, path):
            return [], Image.new("RGB", (1, 1)), None

    class _BoomTagger:
        def embed_image(self, img):
            raise RuntimeError("corrupt model")

    clip_ctx = tagger.ClipTaggingContext(
        tagger=_BoomTagger(), text_embeds=np.zeros((0, 512), dtype=np.float32), threshold=0.24,
    )
    face_count, ok, located, tagged = pipeline.analyze_and_store(
        _StubPipeline(), conn, "2024/a.jpg", 123.0, enrollment={}, threshold=0.45,
        clip_ctx=clip_ctx,
    )
    assert (face_count, ok, located, tagged) == (0, True, False, False)
    assert conn.execute(
        "SELECT COUNT(*) FROM photo_embeddings WHERE photo_path = '2024/a.jpg'"
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT tag FROM photo_tags WHERE photo_path = '2024/a.jpg' AND source = 'ai'"
    ).fetchone()["tag"] == "캠핑"


def test_analyze_and_store_keeps_stale_ai_tags_when_clip_ctx_none(conn):
    """clip_ctx=None(이번 스캔에서 CLIP 모델 로딩 자체가 실패)일 때도 기존 'ai'
    태그를 지우면 안 된다 — 위 테스트와 동일한 이유."""
    from PIL import Image

    _seed_ai_tag(conn, "2024/a.jpg")

    class _StubPipeline:
        def analyze(self, path):
            return [], Image.new("RGB", (1, 1)), None

    pipeline.analyze_and_store(
        _StubPipeline(), conn, "2024/a.jpg", 123.0, enrollment={}, threshold=0.45,
        clip_ctx=None,
    )
    assert conn.execute(
        "SELECT tag FROM photo_tags WHERE photo_path = '2024/a.jpg' AND source = 'ai'"
    ).fetchone()["tag"] == "캠핑"


# ── 카테고리 on/off (얼굴/위치/폴더명/사물) ──────────────────────────


def _make_jpeg(photo_root: str, rel_path: str) -> None:
    from PIL import Image

    abs_path = os.path.join(photo_root, rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    Image.new("RGB", (10, 10)).save(abs_path)


def test_analyze_and_store_face_disabled_preserves_existing_faces(conn):
    """pipeline=None(얼굴 인식 꺼짐)이면 얼굴 검출을 건너뛰고 기존 faces/face_matches를
    건드리지 않는다(DELETE도 안 함) — 끄면 새로 생성만 안 할 뿐 기존 데이터는 보존.

    반환하는 얼굴 수(face_count)는 "이번 스캔에서 새로 검출한 수"를 뜻하므로 항상 0 —
    기존에 남아있던 얼굴 수를 여기 섞으면 재분석할 때마다 실제 검출량과 무관하게
    summary["faces"]/Discord 알림 숫자가 부풀어 오른다. photos_analyzed.face_count는
    별개로 현재 남아있는 행 수(1)를 그대로 기록해야 한다."""
    _make_jpeg(os.getenv("PHOTO_ROOT"), "2024/a.jpg")
    face_id = _insert_face(conn, "2024/a.jpg", _unit_vec(0))
    conn.commit()

    face_count, ok, located, tagged = pipeline.analyze_and_store(
        None, conn, "2024/a.jpg", 123.0, enrollment={}, threshold=0.45,
    )
    assert (face_count, ok, located, tagged) == (0, True, False, False)
    assert conn.execute(
        "SELECT COUNT(*) FROM faces WHERE photo_path = '2024/a.jpg'"
    ).fetchone()[0] == 1
    assert conn.execute(
        "SELECT id FROM faces WHERE photo_path = '2024/a.jpg'"
    ).fetchone()["id"] == face_id
    assert conn.execute(
        "SELECT face_count FROM photos_analyzed WHERE path = '2024/a.jpg'"
    ).fetchone()["face_count"] == 1


def test_analyze_and_store_face_disabled_skips_new_detection(conn):
    """얼굴 인식이 꺼진 상태로 처음 분석되는 사진은 얼굴 0개로 기록되고
    photos_analyzed는 정상적으로 'done'으로 남아야 한다(재스캔 무한 루프 방지)."""
    _make_jpeg(os.getenv("PHOTO_ROOT"), "2024/b.jpg")

    face_count, ok, located, tagged = pipeline.analyze_and_store(
        None, conn, "2024/b.jpg", 123.0, enrollment={}, threshold=0.45,
    )
    assert (face_count, ok, located, tagged) == (0, True, False, False)
    assert conn.execute(
        "SELECT COUNT(*) FROM faces WHERE photo_path = '2024/b.jpg'"
    ).fetchone()[0] == 0
    row = conn.execute(
        "SELECT status, face_count FROM photos_analyzed WHERE path = '2024/b.jpg'"
    ).fetchone()
    assert (row["status"], row["face_count"]) == ("done", 0)


def test_analyze_and_store_location_disabled_preserves_existing_location(conn, monkeypatch):
    """location_enabled=False면 GPS가 있어도 역지오코딩을 호출하지 않고 기존
    photo_locations를 보존해야 한다."""
    from PIL import Image

    conn.execute(
        "INSERT INTO photo_locations (photo_path, city, country) VALUES "
        "('2024/a.jpg', 'Seoul', '대한민국')"
    )
    conn.commit()

    class _StubPipeline:
        def analyze(self, path):
            return [], Image.new("RGB", (1, 1)), (37.5665, 126.978)

    def _boom(*a, **k):
        raise AssertionError("location_enabled=False면 역지오코딩을 호출하면 안 됨")

    monkeypatch.setattr(geocoder, "reverse_geocode", _boom)

    face_count, ok, located, tagged = pipeline.analyze_and_store(
        _StubPipeline(), conn, "2024/a.jpg", 123.0, enrollment={}, threshold=0.45,
        location_enabled=False,
    )
    assert located is False
    loc = conn.execute(
        "SELECT city, country FROM photo_locations WHERE photo_path = '2024/a.jpg'"
    ).fetchone()
    assert (loc["city"], loc["country"]) == ("Seoul", "대한민국")


def test_category_flags_default_all_enabled(conn):
    from ai_worker import main

    assert main.category_flags(conn) == {
        "face_enabled": True, "location_enabled": True,
        "path_enabled": True, "ai_tag_enabled": True,
    }


def test_category_flags_reads_off_values(conn):
    from ai_worker import main

    conn.execute("INSERT INTO ai_settings (key, value) VALUES ('face_enabled', '0')")
    conn.execute("INSERT INTO ai_settings (key, value) VALUES ('ai_tag_enabled', '0')")
    conn.commit()

    assert main.category_flags(conn) == {
        "face_enabled": False, "location_enabled": True,
        "path_enabled": True, "ai_tag_enabled": False,
    }


def test_run_scan_respects_disabled_categories(conn, monkeypatch):
    """face/ai_tag/path가 꺼지면 각각의 무거운 모델 로딩·처리를 아예 건너뛰고,
    켜져 있는 위치(location)만 정상 반영돼야 한다. 대상 사진에 얼굴 인식이 켜져
    있던 과거에 저장된 얼굴이 이미 있는 경우(재분석 시나리오)도 함께 검증한다 —
    summary["faces"]가 "이번 스캔에서 새로 검출한 수"가 아니라 기존에 남아있던
    수까지 합산해버리면, 재스캔할 때마다 실제 검출량과 무관하게 숫자가 부풀어
    오르는 회귀가 생긴다."""
    from ai_worker import main

    conn.execute("INSERT INTO ai_settings (key, value) VALUES ('face_enabled', '0')")
    conn.execute("INSERT INTO ai_settings (key, value) VALUES ('ai_tag_enabled', '0')")
    conn.execute("INSERT INTO ai_settings (key, value) VALUES ('path_enabled', '0')")
    conn.commit()

    class _BoomFacePipeline:
        def __init__(self):
            raise AssertionError("face_enabled=0이면 FacePipeline을 로딩하면 안 됨")

    monkeypatch.setattr(pipeline, "FacePipeline", _BoomFacePipeline)

    class _BoomTagger:
        def __init__(self):
            raise AssertionError("ai_tag_enabled=0이면 ClipTagger를 로딩하면 안 됨")

    monkeypatch.setattr(tagger, "ClipTagger", _BoomTagger)

    def _boom_path_tag(conn):
        raise AssertionError("path_enabled=0이면 폴더명 태깅을 호출하면 안 됨")

    monkeypatch.setattr(scanner, "tag_paths_from_folder_names", _boom_path_tag)
    monkeypatch.setattr(pipeline, "_extract_gps", lambda raw: (37.5665, 126.978))
    monkeypatch.setattr(geocoder, "reverse_geocode", lambda lat, lon: ("Seoul", "대한민국"))

    _make_jpeg(os.getenv("PHOTO_ROOT"), "2024/a.jpg")
    _insert_face(conn, "2024/a.jpg", _unit_vec(0))  # 과거(얼굴 인식이 켜져 있을 때) 저장된 얼굴
    conn.commit()

    summary = main.run_scan()

    assert summary["path_tagged"] == 0
    assert summary["faces"] == 0  # 기존 얼굴이 있어도 "새로 검출"한 게 아니므로 0
    assert summary["tagged"] == 0
    assert summary["located"] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM faces WHERE photo_path = '2024/a.jpg'"
    ).fetchone()[0] == 1  # 기존 얼굴은 삭제되지 않고 그대로 보존
    loc = conn.execute(
        "SELECT city FROM photo_locations WHERE photo_path = '2024/a.jpg'"
    ).fetchone()
    assert loc["city"] == "Seoul"


def test_run_tag_backfill_respects_ai_tag_disabled(conn, monkeypatch):
    """ai_tag_enabled=0이면 CLIP 모델을 로딩하지 않고, 이미 있는 photo_embeddings도
    재채점하지 않아야 한다(끄면 새로 생성 안 함 원칙은 소급 처리에도 동일 적용)."""
    from ai_worker import main

    conn.execute("INSERT INTO ai_settings (key, value) VALUES ('ai_tag_enabled', '0')")
    conn.execute(
        "INSERT INTO photos_analyzed (path, mtime, status) VALUES ('2024/a.jpg', 1.0, 'done')"
    )
    conn.execute(
        "INSERT INTO photo_embeddings (photo_path, embedding) VALUES ('2024/a.jpg', ?)",
        (matcher.embedding_to_blob(_unit_vec(0)),),
    )
    conn.commit()

    class _BoomTagger:
        def __init__(self):
            raise AssertionError("ai_tag_enabled=0이면 ClipTagger를 로딩하면 안 됨")

    monkeypatch.setattr(tagger, "ClipTagger", _BoomTagger)
    monkeypatch.setattr(scanner, "tag_paths_from_folder_names", lambda conn: 0)

    summary = main.run_tag_backfill()
    assert summary["embedded"] == 0
    assert summary["rescored"] == 0


def test_run_tag_backfill_respects_location_disabled(conn, monkeypatch):
    """location_enabled=0이면 사물(AI 태그)은 정상 반영되지만 위치는 채우지 않는다."""
    from ai_worker import main

    conn.execute("INSERT INTO ai_settings (key, value) VALUES ('location_enabled', '0')")
    conn.execute(
        "INSERT INTO photos_analyzed (path, mtime, status) VALUES ('2024/a.jpg', 1.0, 'done')"
    )
    conn.commit()

    monkeypatch.setattr(tag_vocab, "TAG_VOCAB", [{"prompt": "a photo of camping", "label": "캠핑"}])

    class _FakeClipTagger:
        def embed_texts(self, prompts):
            return np.array([[1.0]], dtype=np.float32)

        def embed_image(self, img):
            return np.array([1.0], dtype=np.float32)

    monkeypatch.setattr(tagger, "ClipTagger", _FakeClipTagger)
    monkeypatch.setattr(scanner, "tag_paths_from_folder_names", lambda conn: 0)
    monkeypatch.setattr(pipeline, "_extract_gps", lambda raw: (37.5665, 126.978))
    monkeypatch.setattr(geocoder, "reverse_geocode", lambda lat, lon: ("Seoul", "대한민국"))

    _make_jpeg(os.getenv("PHOTO_ROOT"), "2024/a.jpg")

    summary = main.run_tag_backfill()
    assert summary["located"] == 0
    assert summary["embedded"] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM photo_locations WHERE photo_path = '2024/a.jpg'"
    ).fetchone()[0] == 0


def test_run_tag_backfill_skips_entirely_when_ai_tag_and_location_disabled(conn, monkeypatch):
    """사물·위치가 둘 다 꺼지면 photos_analyzed 대상 조회·CLIP 로딩 없이 즉시 반환한다
    (폴더명 태깅만 켜져 있으면 그 결과만 반영)."""
    from ai_worker import main

    conn.execute("INSERT INTO ai_settings (key, value) VALUES ('ai_tag_enabled', '0')")
    conn.execute("INSERT INTO ai_settings (key, value) VALUES ('location_enabled', '0')")
    conn.execute(
        "INSERT INTO photos_analyzed (path, mtime, status) VALUES ('2024/a.jpg', 1.0, 'done')"
    )
    conn.commit()

    monkeypatch.setattr(scanner, "tag_paths_from_folder_names", lambda conn: 3)

    class _BoomTagger:
        def __init__(self):
            raise AssertionError("사물 인식이 꺼졌으면 CLIP을 로딩하면 안 됨")

    monkeypatch.setattr(tagger, "ClipTagger", _BoomTagger)

    summary = main.run_tag_backfill()
    assert summary == {
        "photos": 0, "embedded": 0, "rescored": 0, "located": 0,
        "errors": 0, "path_tagged": 3, "elapsed": 0.0,
    }


# ── CLIP 사물/장면 태깅 (tag_vocab / tagger) ─────────────────────────


def test_tag_vocab_has_80_unique_entries():
    assert len(tag_vocab.TAG_VOCAB) == 80
    labels = [e["label"] for e in tag_vocab.TAG_VOCAB]
    prompts = [e["prompt"] for e in tag_vocab.TAG_VOCAB]
    assert len(set(labels)) == len(labels)
    assert len(set(prompts)) == len(prompts)
    assert all(e["prompt"] and e["label"] for e in tag_vocab.TAG_VOCAB)


def test_preprocess_image_output_shape():
    from PIL import Image

    img = Image.new("RGB", (640, 480), (10, 20, 30))
    out = tagger._preprocess_image(img)
    assert out.shape == (1, 3, 224, 224)
    assert out.dtype == np.float32


def test_preprocess_image_handles_non_rgb_and_small_images():
    from PIL import Image

    img = Image.new("L", (100, 300))  # 그레이스케일 + 짧은 변 224 미만
    out = tagger._preprocess_image(img)
    assert out.shape == (1, 3, 224, 224)


def test_tag_threshold_setting_db_overrides_env(conn, monkeypatch):
    monkeypatch.setenv("AI_TAG_THRESHOLD", "0.30")
    assert tagger.tag_threshold_setting(conn) == 0.30

    conn.execute(
        "INSERT INTO ai_settings (key, value) VALUES ('tag_threshold', '0.22')"
    )
    conn.commit()
    assert tagger.tag_threshold_setting(conn) == 0.22


def test_tag_threshold_setting_ignores_invalid_db_value(conn, monkeypatch):
    monkeypatch.setenv("AI_TAG_THRESHOLD", "0.24")
    conn.execute(
        "INSERT INTO ai_settings (key, value) VALUES ('tag_threshold', 'not-a-number')"
    )
    conn.commit()
    assert tagger.tag_threshold_setting(conn) == 0.24


def test_download_detects_truncated_response_and_cleans_up_part_file(tmp_path, monkeypatch):
    import io

    class _FakeResponse(io.BytesIO):
        headers = {"Content-Length": "100"}  # 실제 바디(아래)보다 큰 값 → 불완전 응답

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        tagger.urllib.request, "urlopen", lambda url, timeout=60: _FakeResponse(b"short body")
    )
    dest = str(tmp_path / "model.onnx")

    with pytest.raises(OSError):
        tagger._download("http://example.invalid/model.onnx", dest)

    assert not os.path.exists(dest)
    assert not os.path.exists(dest + ".part")


def test_download_succeeds_and_renames_part_file(tmp_path, monkeypatch):
    import io

    body = b"complete model bytes"

    class _FakeResponse(io.BytesIO):
        headers = {"Content-Length": str(len(body))}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        tagger.urllib.request, "urlopen", lambda url, timeout=60: _FakeResponse(body)
    )
    dest = str(tmp_path / "model.onnx")
    tagger._download("http://example.invalid/model.onnx", dest)

    assert os.path.exists(dest)
    assert not os.path.exists(dest + ".part")
    with open(dest, "rb") as f:
        assert f.read() == body


def test_ensure_models_skips_download_when_files_already_exist(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    clip_dir = os.path.join(str(tmp_path / "data"), "models", "clip")
    os.makedirs(clip_dir, exist_ok=True)
    for filename in tagger._MODEL_FILES:
        with open(os.path.join(clip_dir, filename), "wb") as f:
            f.write(b"cached")

    calls = []
    monkeypatch.setattr(tagger, "_download", lambda url, dest: calls.append(dest))
    result_dir = tagger._ensure_models()

    assert result_dir == clip_dir
    assert calls == []  # 이미 존재하는 파일은 재다운로드하지 않음


# ── tag-backfill ─────────────────────────────────────────────────────


def test_rescore_ai_tags_from_cache_reuses_embedding_without_reencoding(conn, monkeypatch):
    """이미 저장된 임베딩을 재사용해 재채점만 한다 — embed_image가 호출되면 안 된다
    (재인코딩 없음이 photo_embeddings를 캐시해두는 핵심 이유)."""
    monkeypatch.setattr(tag_vocab, "TAG_VOCAB", [
        {"prompt": "a photo of camping", "label": "캠핑"},
        {"prompt": "a photo of the sea", "label": "바다"},
    ])
    embed = np.array([1.0, 0.0], dtype=np.float32)
    conn.execute(
        "INSERT INTO photo_embeddings (photo_path, embedding) VALUES (?, ?)",
        ("2024/a.jpg", matcher.embedding_to_blob(embed)),
    )
    conn.commit()

    class _BoomTagger:
        def embed_image(self, img):
            raise AssertionError("재인코딩하면 안 됨")

    clip_ctx = tagger.ClipTaggingContext(
        tagger=_BoomTagger(),
        text_embeds=np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
        threshold=0.5,
    )
    ok = pipeline.rescore_ai_tags_from_cache(conn, "2024/a.jpg", clip_ctx)
    assert ok is True
    tags = {
        r["tag"] for r in conn.execute(
            "SELECT tag FROM photo_tags WHERE photo_path = '2024/a.jpg' AND source = 'ai'"
        )
    }
    assert tags == {"캠핑"}


def test_rescore_ai_tags_from_cache_no_embedding_returns_false(conn):
    clip_ctx = tagger.ClipTaggingContext(
        tagger=None, text_embeds=np.zeros((0, 512), dtype=np.float32), threshold=0.24,
    )
    assert pipeline.rescore_ai_tags_from_cache(conn, "2024/missing.jpg", clip_ctx) is False


def test_rescore_ai_tags_from_cache_none_ctx_returns_false(conn):
    assert pipeline.rescore_ai_tags_from_cache(conn, "2024/a.jpg", None) is False


def test_backfill_photo_fills_embedding_and_location(tmp_path, conn, monkeypatch):
    from PIL import Image

    img_path = tmp_path / "photo.jpg"
    Image.new("RGB", (10, 10), (200, 100, 50)).save(img_path)

    monkeypatch.setattr(pipeline, "_extract_gps", lambda raw: (37.5665, 126.978))
    monkeypatch.setattr(geocoder, "reverse_geocode", lambda lat, lon: ("Seoul", "대한민국"))
    monkeypatch.setattr(tag_vocab, "TAG_VOCAB", [{"prompt": "a photo of camping", "label": "캠핑"}])

    clip_ctx = tagger.ClipTaggingContext(
        tagger=_StubClipTagger(np.array([1.0], dtype=np.float32)),
        text_embeds=np.array([[1.0]], dtype=np.float32),
        threshold=0.5,
    )
    embedded, located = pipeline.backfill_photo(
        conn, "2024/photo.jpg", str(img_path), clip_ctx,
        need_embedding=True, need_location=True,
    )
    assert (embedded, located) == (True, True)
    assert conn.execute(
        "SELECT COUNT(*) FROM photo_embeddings WHERE photo_path = '2024/photo.jpg'"
    ).fetchone()[0] == 1
    loc = conn.execute(
        "SELECT city, country FROM photo_locations WHERE photo_path = '2024/photo.jpg'"
    ).fetchone()
    assert (loc["city"], loc["country"]) == ("Seoul", "대한민국")


def test_backfill_photo_skips_when_not_needed(tmp_path, conn):
    from PIL import Image

    img_path = tmp_path / "photo.jpg"
    Image.new("RGB", (10, 10)).save(img_path)

    embedded, located = pipeline.backfill_photo(
        conn, "2024/photo.jpg", str(img_path), None,
        need_embedding=False, need_location=False,
    )
    assert (embedded, located) == (False, False)


def test_run_tag_backfill_embeds_new_rescopes_cached_and_skips_errors(conn, monkeypatch):
    """photo_embeddings 없는 사진은 새로 인코딩, 있는 사진은 캐시로 재채점만(파일을
    열지 않음), status='error' 사진은 대상에서 제외된다."""
    from ai_worker import main

    monkeypatch.setattr(tag_vocab, "TAG_VOCAB", [
        {"prompt": "a photo of camping", "label": "캠핑"},
        {"prompt": "a photo of the sea", "label": "바다"},
    ])

    class _FakeClipTagger:
        def embed_texts(self, prompts):
            return np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)

        def embed_image(self, img):
            return np.array([1.0, 0.0], dtype=np.float32)

    monkeypatch.setattr(tagger, "ClipTagger", _FakeClipTagger)
    monkeypatch.setattr(scanner, "tag_paths_from_folder_names", lambda conn: 0)

    from PIL import Image

    photo_root = os.getenv("PHOTO_ROOT")
    os.makedirs(os.path.join(photo_root, "2024"), exist_ok=True)
    Image.new("RGB", (10, 10)).save(os.path.join(photo_root, "2024", "a.jpg"))
    # b.jpg는 일부러 만들지 않는다 — embedding+location이 이미 있으면 파일을
    # 열 필요가 없어야 하므로, 파일이 없어도 에러 없이 통과해야 이를 증명한다.

    conn.execute(
        "INSERT INTO photos_analyzed (path, mtime, status) VALUES ('2024/a.jpg', 1.0, 'done')"
    )
    conn.execute(
        "INSERT INTO photos_analyzed (path, mtime, status) VALUES ('2024/b.jpg', 1.0, 'done')"
    )
    conn.execute(
        "INSERT INTO photo_embeddings (photo_path, embedding) VALUES ('2024/b.jpg', ?)",
        (matcher.embedding_to_blob(np.array([0.0, 1.0], dtype=np.float32)),),
    )
    conn.execute(
        "INSERT INTO photo_locations (photo_path, city, country) VALUES "
        "('2024/b.jpg', 'Seoul', '대한민국')"
    )
    conn.execute(
        "INSERT INTO photos_analyzed (path, mtime, status) VALUES ('2024/c.jpg', 1.0, 'error')"
    )
    conn.commit()

    summary = main.run_tag_backfill()

    assert summary["photos"] == 2  # c.jpg(error)는 제외
    assert summary["embedded"] == 1
    assert summary["rescored"] == 1
    assert summary["errors"] == 0  # b.jpg 파일이 없어도 열 필요가 없어 에러가 나면 안 됨

    a_tags = {
        r["tag"] for r in conn.execute(
            "SELECT tag FROM photo_tags WHERE photo_path = '2024/a.jpg' AND source = 'ai'"
        )
    }
    b_tags = {
        r["tag"] for r in conn.execute(
            "SELECT tag FROM photo_tags WHERE photo_path = '2024/b.jpg' AND source = 'ai'"
        )
    }
    assert a_tags == {"캠핑"}
    assert b_tags == {"바다"}


def test_run_tag_backfill_no_targets_skips_model_loading(conn, monkeypatch):
    from ai_worker import main

    monkeypatch.setattr(scanner, "tag_paths_from_folder_names", lambda conn: 0)

    class _BoomTagger:
        def __init__(self):
            raise AssertionError("대상이 없으면 CLIP 모델을 로딩하면 안 됨")

    monkeypatch.setattr(tagger, "ClipTagger", _BoomTagger)
    summary = main.run_tag_backfill()
    assert summary["photos"] == 0


def test_run_tag_backfill_fills_missing_location_end_to_end(conn, monkeypatch):
    """has_location=False → need_location=True 배선이 실제로 photo_locations를
    채우는지 확인한다(개별 backfill_photo는 별도 테스트로 이미 검증했지만, 루프의
    has_location 조회 → need_location 전달 경로는 여기서만 exercise된다)."""
    from ai_worker import main

    monkeypatch.setattr(tag_vocab, "TAG_VOCAB", [{"prompt": "a photo of camping", "label": "캠핑"}])

    class _FakeClipTagger:
        def embed_texts(self, prompts):
            return np.array([[1.0]], dtype=np.float32)

        def embed_image(self, img):
            return np.array([1.0], dtype=np.float32)

    monkeypatch.setattr(tagger, "ClipTagger", _FakeClipTagger)
    monkeypatch.setattr(scanner, "tag_paths_from_folder_names", lambda conn: 0)
    monkeypatch.setattr(pipeline, "_extract_gps", lambda raw: (37.5665, 126.978))
    monkeypatch.setattr(geocoder, "reverse_geocode", lambda lat, lon: ("Seoul", "대한민국"))

    from PIL import Image

    photo_root = os.getenv("PHOTO_ROOT")
    os.makedirs(os.path.join(photo_root, "2024"), exist_ok=True)
    Image.new("RGB", (10, 10)).save(os.path.join(photo_root, "2024", "a.jpg"))

    conn.execute(
        "INSERT INTO photos_analyzed (path, mtime, status) VALUES ('2024/a.jpg', 1.0, 'done')"
    )
    conn.commit()

    summary = main.run_tag_backfill()

    assert summary["located"] == 1
    loc = conn.execute(
        "SELECT city, country FROM photo_locations WHERE photo_path = '2024/a.jpg'"
    ).fetchone()
    assert (loc["city"], loc["country"]) == ("Seoul", "대한민국")


def test_run_tag_backfill_skips_when_photo_root_unmounted(conn, monkeypatch, tmp_path):
    """PHOTO_ROOT가 마운트 해제(빈 디렉터리 또는 미존재)된 상태에서는 대상이 있어도
    CLIP 모델 로딩/파일 열기 없이 즉시 건너뛴다 — scan()의 pending_photos() 보호와
    동일한 취지."""
    from ai_worker import main

    monkeypatch.setattr(scanner, "tag_paths_from_folder_names", lambda conn: 0)

    class _BoomTagger:
        def __init__(self):
            raise AssertionError("마운트 해제 상태면 CLIP 모델을 로딩하면 안 됨")

    monkeypatch.setattr(tagger, "ClipTagger", _BoomTagger)

    conn.execute(
        "INSERT INTO photos_analyzed (path, mtime, status) VALUES ('2024/a.jpg', 1.0, 'done')"
    )
    conn.commit()

    # conn 픽스처가 만든 PHOTO_ROOT는 이미 빈 디렉터리 상태 — 파일을 하나도 넣지 않는다.
    summary = main.run_tag_backfill()
    assert summary["embedded"] == 0
    assert summary["errors"] == 0


# ── matcher ───────────────────────────────────────────────────────────


def test_match_one_picks_best_person_above_threshold():
    enrollment = {
        1: matcher._normalize(np.stack([_unit_vec(0)])),
        2: matcher._normalize(np.stack([_unit_vec(1)])),
    }
    query = _unit_vec(0) * 0.8 + _unit_vec(1) * 0.2
    result = matcher.match_one(query, enrollment, threshold=0.45)
    assert result is not None
    assert result[0] == 1
    assert result[1] > 0.9


def test_match_one_returns_none_below_threshold_or_empty():
    enrollment = {1: matcher._normalize(np.stack([_unit_vec(0)]))}
    assert matcher.match_one(_unit_vec(1), enrollment, threshold=0.45) is None
    assert matcher.match_one(_unit_vec(0), {}, threshold=0.45) is None
    assert matcher.match_one(np.zeros(512), enrollment, threshold=0.45) is None


def test_rematch_all_skips_labeled_faces(conn):
    conn.execute("INSERT INTO persons (name) VALUES ('테스트')")
    enrolled_id = _insert_face(conn, "e.jpg", _unit_vec(0))
    conn.execute(
        "INSERT INTO face_labels (face_id, person_id) VALUES (?, 1)", (enrolled_id,)
    )
    similar_id = _insert_face(conn, "s.jpg", _unit_vec(0))
    _insert_face(conn, "d.jpg", _unit_vec(1))  # 등록 인물과 무관한 얼굴
    conn.commit()

    count = matcher.rematch_all(conn, threshold=0.45)
    assert count == 1
    rows = conn.execute("SELECT face_id, person_id FROM face_matches").fetchall()
    assert [(r["face_id"], r["person_id"]) for r in rows] == [(similar_id, 1)]


def test_rematch_all_streams_across_multiple_batches(conn, monkeypatch):
    """fetchmany 배치 크기를 1로 낮춰 여러 배치에 걸친 스트리밍 경로를 검증."""
    monkeypatch.setattr(matcher, "_REMATCH_FETCH_BATCH", 1)
    conn.execute("INSERT INTO persons (name) VALUES ('테스트')")
    enrolled_id = _insert_face(conn, "e.jpg", _unit_vec(0))
    conn.execute(
        "INSERT INTO face_labels (face_id, person_id) VALUES (?, 1)", (enrolled_id,)
    )
    similar_ids = [_insert_face(conn, f"s{i}.jpg", _unit_vec(0)) for i in range(3)]
    conn.commit()

    count = matcher.rematch_all(conn, threshold=0.45)
    assert count == 3
    rows = conn.execute("SELECT face_id FROM face_matches").fetchall()
    assert {r["face_id"] for r in rows} == set(similar_ids)


def test_rematch_all_clears_stale_matches_when_no_enrollment(conn):
    face_id = _insert_face(conn, "s.jpg", _unit_vec(0))
    conn.execute(
        "INSERT INTO face_matches (face_id, person_id, score) VALUES (?, 1, 0.9)",
        (face_id,),
    )
    conn.commit()

    count = matcher.rematch_all(conn, threshold=0.45)
    assert count == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM face_matches").fetchone()["n"] == 0


def test_embedding_blob_roundtrip():
    vec = np.random.rand(matcher.EMBEDDING_DIM).astype(np.float32)
    assert np.array_equal(matcher.blob_to_embedding(matcher.embedding_to_blob(vec)), vec)


def test_match_ignored_for_person_finds_similar_and_replaces_prior_run(conn):
    conn.execute("INSERT INTO persons (name) VALUES ('테스트')")
    enrolled_id = _insert_face(conn, "e.jpg", _unit_vec(0))
    conn.execute("INSERT INTO face_labels (face_id, person_id) VALUES (?, 1)", (enrolled_id,))

    similar_id = _insert_face(conn, "s.jpg", _unit_vec(0))
    different_id = _insert_face(conn, "d.jpg", _unit_vec(1))
    conn.execute(
        "INSERT INTO face_labels (face_id, person_id) VALUES (?, NULL)", (similar_id,)
    )
    conn.execute(
        "INSERT INTO face_labels (face_id, person_id) VALUES (?, NULL)", (different_id,)
    )
    conn.commit()

    count = matcher.match_ignored_for_person(conn, 1, threshold=0.45)
    assert count == 1
    rows = conn.execute(
        "SELECT face_id, person_id FROM ignored_review_candidates"
    ).fetchall()
    assert [(r["face_id"], r["person_id"]) for r in rows] == [(similar_id, 1)]

    # 재실행 시 이 인물 몫만 DELETE+INSERT로 교체 (같은 결과가 중복 누적되지 않음)
    count2 = matcher.match_ignored_for_person(conn, 1, threshold=0.45)
    assert count2 == 1
    rows2 = conn.execute(
        "SELECT face_id FROM ignored_review_candidates WHERE person_id = 1"
    ).fetchall()
    assert len(rows2) == 1


def test_match_ignored_for_person_ignores_labeled_faces(conn):
    """face_labels가 있는(무시 아닌) 얼굴은 후보 대상에서 제외."""
    conn.execute("INSERT INTO persons (name) VALUES ('테스트')")
    enrolled_id = _insert_face(conn, "e.jpg", _unit_vec(0))
    conn.execute("INSERT INTO face_labels (face_id, person_id) VALUES (?, 1)", (enrolled_id,))
    labeled_similar = _insert_face(conn, "l.jpg", _unit_vec(0))
    conn.execute(
        "INSERT INTO face_labels (face_id, person_id) VALUES (?, 1)", (labeled_similar,)
    )
    conn.commit()

    count = matcher.match_ignored_for_person(conn, 1, threshold=0.45)
    assert count == 0


def test_match_ignored_for_person_no_enrollment_clears_candidates(conn):
    conn.execute("INSERT INTO persons (name) VALUES ('테스트')")
    ignored_id = _insert_face(conn, "s.jpg", _unit_vec(0))
    conn.execute(
        "INSERT INTO face_labels (face_id, person_id) VALUES (?, NULL)", (ignored_id,)
    )
    conn.execute(
        "INSERT INTO ignored_review_candidates (face_id, person_id, score) VALUES (?, 1, 0.9)",
        (ignored_id,),
    )
    conn.commit()

    count = matcher.match_ignored_for_person(conn, 1, threshold=0.45)
    assert count == 0
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM ignored_review_candidates"
    ).fetchone()["n"] == 0


# ── daemon ────────────────────────────────────────────────────────────


def test_next_scan_time_today_and_tomorrow():
    from datetime import datetime

    from ai_worker.daemon import next_scan_time

    before = datetime(2026, 7, 7, 1, 30)
    assert next_scan_time(before, 2) == datetime(2026, 7, 7, 2, 0)
    after = datetime(2026, 7, 7, 2, 0)  # 정각 이후는 다음 날
    assert next_scan_time(after, 2) == datetime(2026, 7, 8, 2, 0)


def test_claim_and_finish_job_lifecycle(conn):
    from ai_worker.daemon import claim_next_job, finish_job

    assert claim_next_job(conn) is None  # 빈 큐
    conn.execute("INSERT INTO jobs (type) VALUES ('scan')")
    conn.execute("INSERT INTO jobs (type) VALUES ('rematch')")
    conn.commit()

    job_id, job_type, target_person_id = claim_next_job(conn)  # 오래된 잡 우선
    assert job_type == "scan"
    assert target_person_id is None
    assert conn.execute(
        "SELECT status FROM jobs WHERE id=?", (job_id,)
    ).fetchone()[0] == "running"

    finish_job(conn, job_id, "done")
    row = conn.execute(
        "SELECT status, finished_at FROM jobs WHERE id=?", (job_id,)
    ).fetchone()
    assert row["status"] == "done" and row["finished_at"] is not None

    assert claim_next_job(conn)[1] == "rematch"  # 다음 잡


def test_claim_next_job_returns_target_person_id(conn):
    from ai_worker.daemon import claim_next_job

    conn.execute(
        "INSERT INTO jobs (type, target_person_id) VALUES ('review_ignored', 7)"
    )
    conn.commit()

    job_id, job_type, target_person_id = claim_next_job(conn)
    assert job_type == "review_ignored"
    assert target_person_id == 7


def test_reset_stale_jobs(conn):
    from ai_worker.daemon import reset_stale_jobs

    conn.execute("INSERT INTO jobs (type, status) VALUES ('scan', 'running')")
    conn.execute("INSERT INTO jobs (type, status) VALUES ('scan', 'done')")
    conn.commit()
    assert reset_stale_jobs(conn) == 1
    statuses = [r[0] for r in conn.execute("SELECT status FROM jobs ORDER BY id")]
    assert statuses == ["pending", "done"]


def test_scan_hour_setting_db_overrides_env(conn, monkeypatch):
    from ai_worker.daemon import scan_hour_setting

    monkeypatch.setenv("AI_SCAN_HOUR", "3")
    assert scan_hour_setting(conn) == 3  # 미설정 → 환경변수

    conn.execute("INSERT OR REPLACE INTO ai_settings (key, value) VALUES ('scan_hour', '5')")
    conn.commit()
    assert scan_hour_setting(conn) == 5  # DB 설정 우선

    # 잘못된 값(범위 밖/비숫자)은 환경변수로 폴백
    conn.execute("UPDATE ai_settings SET value='24' WHERE key='scan_hour'")
    conn.commit()
    assert scan_hour_setting(conn) == 3
    conn.execute("UPDATE ai_settings SET value='abc' WHERE key='scan_hour'")
    conn.commit()
    assert scan_hour_setting(conn) == 3


# ── label_sheet ───────────────────────────────────────────────────────


def test_greedy_cluster_groups_similar_vectors():
    from ai_worker.tools.label_sheet import greedy_cluster

    embs = matcher._normalize(np.stack([
        _unit_vec(0),
        _unit_vec(0) * 0.9 + _unit_vec(5) * 0.1,  # 0번과 유사
        _unit_vec(1),
        _unit_vec(0) * 0.95 + _unit_vec(6) * 0.05,  # 0번과 유사
    ]))
    clusters = greedy_cluster(embs, threshold=0.5)
    assert sorted(clusters, key=min) == [[0, 1, 3], [2]]


# ── label_helper ──────────────────────────────────────────────────────


def test_label_import_creates_person_and_null_label(conn, tmp_path, monkeypatch):
    from ai_worker.tools import label_helper

    face_a = _insert_face(conn, "a.jpg", _unit_vec(0))
    face_b = _insert_face(conn, "b.jpg", _unit_vec(1))
    face_c = _insert_face(conn, "c.jpg", _unit_vec(2))
    conn.commit()

    csv_path = tmp_path / "labels.csv"
    csv_path.write_text(
        "face_id,crop,photo_path,person\n"
        f"{face_a},x,a.jpg,지우\n"
        f"{face_b},x,b.jpg,-\n"
        f"{face_c},x,c.jpg,\n",
        encoding="utf-8-sig",
    )
    label_helper.import_csv(str(csv_path))

    check = db.connect()
    labels = {
        row["face_id"]: row["person_id"]
        for row in check.execute("SELECT face_id, person_id FROM face_labels")
    }
    assert labels == {face_a: 1, face_b: None}  # 빈칸(face_c)은 건너뜀
    assert check.execute("SELECT name FROM persons").fetchone()["name"] == "지우"


# ── main.run_scan (Discord 알림용 요약) ──────────────────────────────


def test_run_scan_reports_total_pending_repairs_and_orphans(conn):
    """renamed/orphaned는 이번 스캔에서 새로 쌓인 건수가 아니라, admin이 아직
    승인/거부하지 않은 전체 누적 건수여야 한다 (과거 스캔에서 쌓인 것 포함)."""
    from ai_worker import main

    conn.execute(
        "INSERT INTO pending_path_repairs (old_path, new_path, source) "
        "VALUES ('old/a.jpg', 'new/a.jpg', 'scan')"
    )
    conn.execute(
        "INSERT INTO pending_orphan_cleanups (path, source) VALUES ('gone/b.jpg', 'scan')"
    )
    conn.commit()

    summary = main.run_scan()

    assert summary["photos"] == 0  # 빈 PHOTO_ROOT → 분석 대상 없음, insightface 로딩 없이 종료
    assert summary["renamed"] == 1
    assert summary["orphaned"] == 1


def test_run_scan_empty_pending_skips_pipeline(conn):
    """분석 대상이 없으면 FacePipeline(insightface) 로딩 없이 바로 요약을 반환해야 한다."""
    from ai_worker import main

    summary = main.run_scan()
    assert summary == {
        "photos": 0, "faces": 0, "errors": 0, "located": 0, "tagged": 0,
        "renamed": 0, "orphaned": 0, "elapsed": 0.0, "path_tagged": 0,
    }


# ── notify ────────────────────────────────────────────────────────────


def test_notify_send_skips_when_webhook_unset(monkeypatch):
    from ai_worker import notify

    monkeypatch.delenv("AI_DISCORD_WEBHOOK_URL", raising=False)
    calls = []
    monkeypatch.setattr(notify.urllib.request, "urlopen", lambda *a, **k: calls.append(1))

    notify.notify_rematch_result({"matched": 3})

    assert calls == []


def test_notify_send_retries_up_to_three_times_then_gives_up(monkeypatch):
    from ai_worker import notify

    monkeypatch.setenv("AI_DISCORD_WEBHOOK_URL", "https://example.invalid/webhook")
    monkeypatch.setattr(notify.time, "sleep", lambda s: None)  # 재시도 대기 스킵

    attempts = []

    def failing_urlopen(*a, **k):
        attempts.append(1)
        raise OSError("network down")

    monkeypatch.setattr(notify.urllib.request, "urlopen", failing_urlopen)

    notify.notify_rematch_result({"matched": 1})  # 예외를 밖으로 던지지 않아야 함

    assert len(attempts) == 3


def test_notify_send_succeeds_on_first_try_without_retry(monkeypatch):
    from ai_worker import notify

    monkeypatch.setenv("AI_DISCORD_WEBHOOK_URL", "https://example.invalid/webhook")
    slept = []
    monkeypatch.setattr(notify.time, "sleep", lambda s: slept.append(s))

    attempts = []
    monkeypatch.setattr(
        notify.urllib.request, "urlopen", lambda *a, **k: attempts.append(1)
    )

    notify.notify_rematch_result({"matched": 1})

    assert len(attempts) == 1
    assert slept == []


def test_notify_tag_backfill_result_formats_summary(monkeypatch):
    """run_tag_backfill()이 반환하는 summary dict의 키(photos/embedded/rescored/
    located/errors/path_tagged/elapsed)가 notify_tag_backfill_result의 f-string과
    어긋나면 KeyError가 나야 하는데, 이걸 잡아줄 테스트가 없었다 — 키 이름을
    바꾸는 리팩토링이 있어도 여기서 바로 드러나게 한다."""
    from ai_worker import notify

    monkeypatch.setenv("AI_DISCORD_WEBHOOK_URL", "https://example.invalid/webhook")
    monkeypatch.setenv("BASE_URL", "http://example.test:9999")

    sent = {}

    def fake_urlopen(req, timeout=None):
        import json
        sent["content"] = json.loads(req.data)["content"]

    monkeypatch.setattr(notify.urllib.request, "urlopen", fake_urlopen)

    notify.notify_tag_backfill_result({
        "photos": 5, "embedded": 2, "rescored": 3, "located": 1,
        "errors": 0, "path_tagged": 4, "elapsed": 12.3,
    })

    assert "사진 5장 대상" in sent["content"]
    assert "신규 임베딩 2장" in sent["content"]
    assert "재채점 3장" in sent["content"]
    assert "위치보완 1장" in sent["content"]
    assert "에러 0건" in sent["content"]
    assert "폴더명 태깅 4장" in sent["content"]
    assert "소요 12초" in sent["content"]
    assert "http://example.test:9999/admin/people" in sent["content"]


def test_notify_location_tag_reset_result_formats_summary(monkeypatch):
    """run_location_tag_reset()이 반환하는 summary dict의 키(translated/elapsed)가
    notify_location_tag_reset_result의 f-string과 어긋나면 KeyError가 나야 한다."""
    from ai_worker import notify

    monkeypatch.setenv("AI_DISCORD_WEBHOOK_URL", "https://example.invalid/webhook")
    monkeypatch.setenv("BASE_URL", "http://example.test:9999")

    sent = {}

    def fake_urlopen(req, timeout=None):
        import json
        sent["content"] = json.loads(req.data)["content"]

    monkeypatch.setattr(notify.urllib.request, "urlopen", fake_urlopen)

    notify.notify_location_tag_reset_result({"translated": 7, "elapsed": 3.4})

    assert "도시명 7건 한글 변환" in sent["content"]
    assert "소요 3초" in sent["content"]
    assert "http://example.test:9999/admin/people" in sent["content"]


def _scan_summary(**overrides) -> dict:
    base = {
        "photos": 3, "faces": 2, "errors": 0, "located": 1, "tagged": 2,
        "path_tagged": 0, "renamed": 1, "orphaned": 0, "elapsed": 1.5,
    }
    base.update(overrides)
    return base


def test_notify_scan_result_includes_admin_people_link(tmp_path, monkeypatch):
    from ai_worker import notify

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AI_DISCORD_WEBHOOK_URL", "https://example.invalid/webhook")
    monkeypatch.setenv("BASE_URL", "http://example.test:9999")

    sent = {}

    def fake_urlopen(req, timeout=None):
        import json
        sent["content"] = json.loads(req.data)["content"]

    monkeypatch.setattr(notify.urllib.request, "urlopen", fake_urlopen)

    notify.notify_scan_result(_scan_summary())

    assert "http://example.test:9999/admin/people" in sent["content"]
    assert "위치 1건" in sent["content"]
    assert "태그 2건" in sent["content"]


def test_notify_scan_result_skips_when_no_increment(tmp_path, monkeypatch):
    """이번 스캔이 아무것도 처리하지 않았고(photos=0, path_tagged=0) 경로 변경·
    삭제 승인 대기 누적치도 직전 발송값과 같으면 webhook을 보내지 않아야 한다
    (2026-08-02 사용자 피드백: 증분 없는 날도 매번 알림이 와서 소음이 됨)."""
    from ai_worker import notify

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AI_DISCORD_WEBHOOK_URL", "https://example.invalid/webhook")

    calls = []
    monkeypatch.setattr(notify.urllib.request, "urlopen", lambda *a, **k: calls.append(1))

    # 최초 발송 — 상태 파일이 없으므로(직전 발송값 없음) 무조건 보낸다.
    notify.notify_scan_result(
        _scan_summary(photos=0, faces=0, located=0, tagged=0, path_tagged=0,
                      renamed=1, orphaned=0)
    )
    assert len(calls) == 1

    # 증분 없이 재실행 — renamed/orphaned도 직전 발송값과 동일 → 스킵.
    notify.notify_scan_result(
        _scan_summary(photos=0, faces=0, located=0, tagged=0, path_tagged=0,
                      renamed=1, orphaned=0)
    )
    assert len(calls) == 1

    # renamed pending 누적치가 늘어남 → 다시 보낸다.
    notify.notify_scan_result(
        _scan_summary(photos=0, faces=0, located=0, tagged=0, path_tagged=0,
                      renamed=2, orphaned=0)
    )
    assert len(calls) == 2

    # 처리한 사진이 있으면(photos>0) pending 변화가 없어도 보낸다.
    notify.notify_scan_result(
        _scan_summary(photos=5, faces=1, located=0, tagged=0, path_tagged=0,
                      renamed=2, orphaned=0)
    )
    assert len(calls) == 3
