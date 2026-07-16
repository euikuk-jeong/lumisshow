"""임베딩 cosine similarity 매칭. 10만 임베딩 규모까지 numpy brute-force로 충분."""

import sqlite3

import numpy as np

EMBEDDING_DIM = 512


def embedding_to_blob(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def blob_to_embedding(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def _normalize(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


def load_enrollment(conn: sqlite3.Connection) -> dict[int, np.ndarray]:
    """face_labels에서 인물별 등록 임베딩 행렬 {person_id: (n, 512)} 로드."""
    rows = conn.execute(
        """SELECT fl.person_id, f.embedding
           FROM face_labels fl JOIN faces f ON f.id = fl.face_id
           WHERE fl.person_id IS NOT NULL"""
    ).fetchall()
    grouped: dict[int, list[np.ndarray]] = {}
    for row in rows:
        grouped.setdefault(row["person_id"], []).append(
            blob_to_embedding(row["embedding"])
        )
    return {
        pid: _normalize(np.stack(vecs)) for pid, vecs in grouped.items()
    }


def match_one(
    embedding: np.ndarray,
    enrollment: dict[int, np.ndarray],
    threshold: float,
) -> tuple[int, float] | None:
    """등록 임베딩과 비교해 (person_id, score) 반환. 임계값 미달이면 None.

    인물별 점수 = 그 인물의 등록 얼굴들과의 cosine similarity 최댓값.
    """
    vec = np.asarray(embedding, dtype=np.float32)
    norm = np.linalg.norm(vec)
    if norm == 0 or not enrollment:
        return None
    vec = vec / norm

    best_pid, best_score = None, -1.0
    for pid, mat in enrollment.items():
        score = float((mat @ vec).max())
        if score > best_score:
            best_pid, best_score = pid, score
    if best_score >= threshold:
        return best_pid, best_score
    return None


_REMATCH_FETCH_BATCH = 2000


def rematch_all(conn: sqlite3.Connection, threshold: float) -> int:
    """모든 얼굴을 현재 등록 셋 기준으로 재매칭. face_matches 전체 갱신.

    사람이 라벨한 얼굴(face_labels 존재)은 매칭 대상에서 제외 —
    유효 인물 판정에서 라벨이 항상 우선하므로 계산 낭비만 되기 때문.
    갱신된 face_matches 행 수를 반환.
    """
    enrollment = load_enrollment(conn)
    cursor = conn.execute(
        """SELECT f.id, f.embedding FROM faces f
           LEFT JOIN face_labels fl ON fl.face_id = f.id
           WHERE fl.face_id IS NULL"""
    )

    # 매칭 계산은 트랜잭션 밖에서 — 수만 얼굴 계산 동안 쓰기 락을 잡으면
    # LumisShow의 face_labels 쓰기가 busy_timeout 초과로 실패한다.
    # fetchmany로 배치 스트리밍 — 전체 임베딩을 한 번에 메모리에 올리지 않음.
    matches = []
    while True:
        batch = cursor.fetchmany(_REMATCH_FETCH_BATCH)
        if not batch:
            break
        for row in batch:
            result = match_one(blob_to_embedding(row["embedding"]), enrollment, threshold)
            if result is not None:
                matches.append((row["id"], result[0], result[1]))

    conn.execute("DELETE FROM face_matches")
    conn.executemany(
        "INSERT INTO face_matches (face_id, person_id, score) VALUES (?, ?, ?)",
        matches,
    )
    conn.commit()
    return len(matches)
