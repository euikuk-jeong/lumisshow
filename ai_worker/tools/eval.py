"""정확도 평가 도구 (M1 성공 기준: 가족 recall 90%+ / precision 95%+).

face_labels의 라벨을 인물별로 등록(enroll) / 검증(test)으로 나누고,
등록 셋만으로 검증 셋을 매칭해 threshold별 precision/recall을 출력한다.
person_id가 NULL인 라벨(타인 '-')은 음성(negative) 샘플로 사용.

  python -m ai_worker.tools.eval [--enroll 10] [--thresholds 0.30,0.35,...]
"""

import argparse
from collections import defaultdict

import numpy as np

from ai_worker import db, matcher


def load_labeled(conn):
    """인물별 (임베딩 목록), 그리고 음성 임베딩 목록을 반환."""
    rows = conn.execute(
        """SELECT fl.person_id, f.embedding FROM face_labels fl
           JOIN faces f ON f.id = fl.face_id"""
    ).fetchall()
    by_person: dict[int, list[np.ndarray]] = defaultdict(list)
    negatives: list[np.ndarray] = []
    for row in rows:
        vec = matcher.blob_to_embedding(row["embedding"])
        if row["person_id"] is None:
            negatives.append(vec)
        else:
            by_person[row["person_id"]].append(vec)
    return by_person, negatives


def evaluate(by_person, negatives, enroll_n: int, threshold: float):
    """(person_id → (tp, fn), 전체 fp 수, 예측 총수) 계산."""
    enrollment = {
        pid: matcher._normalize(np.stack(vecs[:enroll_n]))
        for pid, vecs in by_person.items()
        if len(vecs) > enroll_n  # 검증 샘플이 최소 1개 남는 인물만
    }
    stats = {pid: [0, 0] for pid in enrollment}  # [tp, fn]
    fp = 0
    for pid, vecs in by_person.items():
        if pid not in enrollment:
            continue
        for vec in vecs[enroll_n:]:
            result = matcher.match_one(vec, enrollment, threshold)
            if result is not None and result[0] == pid:
                stats[pid][0] += 1
            else:
                stats[pid][1] += 1
                if result is not None:
                    fp += 1  # 다른 인물로 오인
    for vec in negatives:
        if matcher.match_one(vec, enrollment, threshold) is not None:
            fp += 1  # 타인을 등록 인물로 오인
    return stats, fp


def main() -> None:
    parser = argparse.ArgumentParser(prog="eval")
    parser.add_argument("--enroll", type=int, default=10,
                        help="인물별 등록에 사용할 얼굴 수 (기본 10)")
    parser.add_argument("--thresholds", default="0.30,0.35,0.40,0.45,0.50,0.55,0.60")
    args = parser.parse_args()

    conn = db.connect()
    by_person, negatives = load_labeled(conn)
    names = {row["id"]: row["name"] for row in conn.execute("SELECT id, name FROM persons")}
    print(f"라벨: 인물 {len(by_person)}명 "
          f"({sum(len(v) for v in by_person.values())}얼굴), 음성 {len(negatives)}얼굴")

    for th in (float(t) for t in args.thresholds.split(",")):
        stats, fp = evaluate(by_person, negatives, args.enroll, th)
        tp_all = sum(tp for tp, _ in stats.values())
        fn_all = sum(fn for _, fn in stats.values())
        recall = tp_all / (tp_all + fn_all) if tp_all + fn_all else 0.0
        precision = tp_all / (tp_all + fp) if tp_all + fp else 0.0
        print(f"\n== threshold {th:.2f}: precision {precision:.1%}, recall {recall:.1%} "
              f"(TP {tp_all}, FN {fn_all}, FP {fp})")
        for pid, (tp, fn) in sorted(stats.items()):
            r = tp / (tp + fn) if tp + fn else 0.0
            print(f"   {names.get(pid, pid)}: recall {r:.1%} ({tp}/{tp + fn})")


if __name__ == "__main__":
    main()
