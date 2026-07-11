"""ai_worker 단위 테스트 — 모델(insightface) 설치 없이 실행 가능한 범위:
db 스키마, 증분 스캐너, cosine 매처, 라벨링 도구."""

import os
import time

import numpy as np
import pytest

from ai_worker import db, matcher, scanner


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
    assert {"photos_analyzed", "faces", "face_matches",
            "persons", "face_labels", "jobs"} <= tables


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


def test_embedding_blob_roundtrip():
    vec = np.random.rand(matcher.EMBEDDING_DIM).astype(np.float32)
    assert np.array_equal(matcher.blob_to_embedding(matcher.embedding_to_blob(vec)), vec)


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

    job_id, job_type = claim_next_job(conn)  # 오래된 잡 우선
    assert job_type == "scan"
    assert conn.execute(
        "SELECT status FROM jobs WHERE id=?", (job_id,)
    ).fetchone()[0] == "running"

    finish_job(conn, job_id, "done")
    row = conn.execute(
        "SELECT status, finished_at FROM jobs WHERE id=?", (job_id,)
    ).fetchone()
    assert row["status"] == "done" and row["finished_at"] is not None

    assert claim_next_job(conn)[1] == "rematch"  # 다음 잡


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
