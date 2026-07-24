"""워커 CLI 진입점.

  python -m ai_worker.main scan     # 증분 스캔 → 분석 → 매칭 (1회)
  python -m ai_worker.main rematch  # 전체 얼굴을 현재 등록 셋으로 재매칭
  python -m ai_worker.main daemon   # 야간 자동 스캔 + jobs 큐 폴링 (컨테이너 상주)
"""

import argparse
import logging
import random
import time

from ai_worker import config, db, matcher, scanner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ai_worker")


def _pending_repair_count(conn) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM pending_path_repairs WHERE status='pending'"
    ).fetchone()[0]


def _pending_orphan_count(conn) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM pending_orphan_cleanups WHERE status='pending'"
    ).fetchone()[0]


def run_scan(limit: int | None = None) -> dict:
    from ai_worker.pipeline import FacePipeline, analyze_and_store

    conn = db.connect()
    root = config.photo_root()
    pending = scanner.pending_photos(conn, root)
    renamed = _pending_repair_count(conn)
    orphaned = _pending_orphan_count(conn)
    log.info("스캔 완료: 분석 대상 %d장 (root=%s), 경로 변경 승인 대기 %d건, 삭제 승인 대기 %d건",
             len(pending), root, renamed, orphaned)
    if limit is not None and len(pending) > limit:
        # 샘플링 검증용: 전체에서 균등 랜덤 추출 (시드 고정 → 재실행 시 이어서 진행 가능)
        pending = random.Random(42).sample(pending, limit)
        log.info("--limit %d: 랜덤 샘플 %d장만 처리", limit, len(pending))

    summary = {
        "photos": len(pending), "faces": 0, "errors": 0,
        "renamed": renamed, "orphaned": orphaned, "elapsed": 0.0,
    }
    if not pending:
        return summary

    log.info("모델 로딩 중 (buffalo_l, det_size=%d)...", config.det_size())
    pipeline = FacePipeline()
    enrollment = matcher.load_enrollment(conn)
    threshold = config.match_threshold()
    log.info("등록 인물 %d명, threshold=%.2f", len(enrollment), threshold)

    start = time.monotonic()
    total_faces = 0
    errors = 0
    for i, (rel_path, mtime) in enumerate(pending, 1):
        face_count, ok = analyze_and_store(
            pipeline, conn, rel_path, mtime, enrollment, threshold
        )
        total_faces += face_count
        if not ok:
            errors += 1
        if i % 100 == 0:
            elapsed = time.monotonic() - start
            log.info(
                "%d/%d장 처리 (%.1f초/장, 얼굴 %d개)",
                i, len(pending), elapsed / i, total_faces,
            )
    elapsed = time.monotonic() - start
    log.info("완료: %d장, 얼굴 %d개, 에러 %d건, %.0f초", len(pending), total_faces,
             errors, elapsed)

    summary["faces"] = total_faces
    summary["errors"] = errors
    summary["elapsed"] = elapsed
    return summary


def run_rematch() -> dict:
    conn = db.connect()
    count = matcher.rematch_all(conn, config.match_threshold())
    log.info("재매칭 완료: %d개 얼굴 매칭됨", count)
    return {"matched": count}


def run_review_ignored(target_person_id: int) -> None:
    conn = db.connect()
    count = matcher.match_ignored_for_person(conn, target_person_id, config.match_threshold())
    log.info("무시 얼굴 재검토 완료 (인물 #%d): 후보 %d개", target_person_id, count)


def main() -> None:
    parser = argparse.ArgumentParser(prog="ai_worker")
    parser.add_argument("command", choices=["scan", "rematch", "daemon"])
    parser.add_argument("--limit", type=int, default=None,
                        help="최대 처리 장수 (전체에서 균등 랜덤 샘플)")
    args = parser.parse_args()
    if args.command == "scan":
        run_scan(args.limit)
    elif args.command == "rematch":
        run_rematch()
    else:
        from ai_worker.daemon import run_daemon
        run_daemon()


if __name__ == "__main__":
    main()
