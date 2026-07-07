"""워커 CLI 진입점.

  python -m ai_worker.main scan     # 증분 스캔 → 분석 → 매칭 (1회)
  python -m ai_worker.main rematch  # 전체 얼굴을 현재 등록 셋으로 재매칭

야간 스케줄/jobs 큐 폴링 데몬 모드는 M2에서 추가.
"""

import argparse
import logging
import random
import time

from ai_worker import config, db, matcher, scanner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ai_worker")


def run_scan(limit: int | None = None) -> None:
    from ai_worker.pipeline import FacePipeline, analyze_and_store

    conn = db.connect()
    root = config.photo_root()
    pending = scanner.pending_photos(conn, root)
    log.info("스캔 완료: 분석 대상 %d장 (root=%s)", len(pending), root)
    if limit is not None and len(pending) > limit:
        # 샘플링 검증용: 전체에서 균등 랜덤 추출 (시드 고정 → 재실행 시 이어서 진행 가능)
        pending = random.Random(42).sample(pending, limit)
        log.info("--limit %d: 랜덤 샘플 %d장만 처리", limit, len(pending))
    if not pending:
        return

    log.info("모델 로딩 중 (buffalo_l, det_size=%d)...", config.det_size())
    pipeline = FacePipeline()
    enrollment = matcher.load_enrollment(conn)
    threshold = config.match_threshold()
    log.info("등록 인물 %d명, threshold=%.2f", len(enrollment), threshold)

    start = time.monotonic()
    total_faces = 0
    for i, (rel_path, mtime) in enumerate(pending, 1):
        total_faces += analyze_and_store(
            pipeline, conn, rel_path, mtime, enrollment, threshold
        )
        if i % 100 == 0:
            elapsed = time.monotonic() - start
            log.info(
                "%d/%d장 처리 (%.1f초/장, 얼굴 %d개)",
                i, len(pending), elapsed / i, total_faces,
            )
    log.info("완료: %d장, 얼굴 %d개, %.0f초", len(pending), total_faces,
             time.monotonic() - start)


def run_rematch() -> None:
    conn = db.connect()
    count = matcher.rematch_all(conn, config.match_threshold())
    log.info("재매칭 완료: %d개 얼굴 매칭됨", count)


def main() -> None:
    parser = argparse.ArgumentParser(prog="ai_worker")
    parser.add_argument("command", choices=["scan", "rematch"])
    parser.add_argument("--limit", type=int, default=None,
                        help="최대 처리 장수 (전체에서 균등 랜덤 샘플)")
    args = parser.parse_args()
    if args.command == "scan":
        run_scan(args.limit)
    else:
        run_rematch()


if __name__ == "__main__":
    main()
