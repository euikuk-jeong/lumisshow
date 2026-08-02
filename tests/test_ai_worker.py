"""ai_worker 단위 테스트 — 모델(insightface) 설치 없이 실행 가능한 범위:
db 스키마, 증분 스캐너, cosine 매처, 라벨링 도구."""

import os
import time

import numpy as np
import pytest

from ai_worker import db, geocoder, matcher, pipeline, scanner


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
            "pending_orphan_cleanups", "photo_tags", "photo_locations"} <= tables


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


def test_tag_paths_from_folder_names_retries_zero_noun_folders_every_scan(conn, monkeypatch):
    """순수 영문/숫자 폴더처럼 명사가 하나도 안 나오면 태그 행이 생기지 않아 커버리지
    쿼리가 매 스캔 다시 대상으로 잡는다 — 의도된 동작(비용이 낮아 최적화 보류)."""
    fake = _CountingKiwi({"IMG_2024": []})
    monkeypatch.setattr(scanner, "_get_kiwi", lambda: fake)
    conn.execute("INSERT INTO photos_analyzed (path, mtime) VALUES ('2024/IMG_2024/a.jpg', 0)")
    conn.commit()

    assert scanner.tag_paths_from_folder_names(conn) == 1
    assert conn.execute("SELECT COUNT(*) FROM photo_tags").fetchone()[0] == 0

    assert scanner.tag_paths_from_folder_names(conn) == 1
    assert fake.calls == 2


def test_tag_paths_from_folder_names_no_pending_returns_zero(conn):
    assert scanner.tag_paths_from_folder_names(conn) == 0


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


def test_reverse_geocode_maps_country_code_to_korean(monkeypatch):
    class _FakeGeocoder:
        def query(self, coords):
            return [{"name": "Seoul", "cc": "KR"}]

    monkeypatch.setattr(geocoder, "_get_geocoder", lambda: _FakeGeocoder())
    city, country = geocoder.reverse_geocode(37.5665, 126.978)
    assert city == "Seoul"
    assert country == "대한민국"


def test_reverse_geocode_falls_back_to_raw_code_when_unmapped(monkeypatch):
    class _FakeGeocoder:
        def query(self, coords):
            return [{"name": "Nowhere", "cc": "ZZ"}]

    monkeypatch.setattr(geocoder, "_get_geocoder", lambda: _FakeGeocoder())
    city, country = geocoder.reverse_geocode(0.0, 0.0)
    assert city == "Nowhere"
    assert country == "ZZ"


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


def test_analyze_and_store_persists_location_from_stub_pipeline(conn, monkeypatch):
    """pipeline.analyze()가 (faces, img, gps) 3-tuple을 반환하도록 바뀐 계약과
    analyze_and_store의 언패킹·photo_locations/photo_tags 기록까지 실제 함수
    경로로 검증(insightface 없이 스텁 파이프라인 사용)."""
    from PIL import Image

    monkeypatch.setattr(geocoder, "reverse_geocode", lambda lat, lon: ("Seoul", "대한민국"))

    class _StubPipeline:
        def analyze(self, path):
            return [], Image.new("RGB", (1, 1)), (37.5665, 126.978)

    face_count, ok = pipeline.analyze_and_store(
        _StubPipeline(), conn, "2024/a.jpg", 123.0, enrollment={}, threshold=0.45
    )
    assert (face_count, ok) == (0, True)

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
        "photos": 0, "faces": 0, "errors": 0,
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


def test_notify_scan_result_includes_admin_people_link(monkeypatch):
    from ai_worker import notify

    monkeypatch.setenv("AI_DISCORD_WEBHOOK_URL", "https://example.invalid/webhook")
    monkeypatch.setenv("BASE_URL", "http://example.test:9999")

    sent = {}

    def fake_urlopen(req, timeout=None):
        import json
        sent["content"] = json.loads(req.data)["content"]

    monkeypatch.setattr(notify.urllib.request, "urlopen", fake_urlopen)

    notify.notify_scan_result(
        {"photos": 3, "faces": 2, "errors": 0, "renamed": 1, "orphaned": 0, "elapsed": 1.5}
    )

    assert "http://example.test:9999/admin/people" in sent["content"]
