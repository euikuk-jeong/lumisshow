"""워커 CLI 진입점.

  python -m ai_worker.main scan          # 증분 스캔 → 분석 → 매칭 (1회)
  python -m ai_worker.main rematch       # 전체 얼굴을 현재 등록 셋으로 재매칭
  python -m ai_worker.main tag-backfill  # AI 태그/위치 재계산(어휘·threshold 변경 후,
                                          # 또는 이 기능 도입 이전 사진 소급 적용)
  python -m ai_worker.main daemon        # 야간 자동 스캔 + jobs 큐 폴링 (컨테이너 상주)
"""

import argparse
import logging
import os
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


_CATEGORY_KEYS = ("face_enabled", "location_enabled", "path_enabled", "ai_tag_enabled")


def category_flags(conn) -> dict[str, bool]:
    """ai_settings의 카테고리별 on/off(Admin 설정). 키가 없으면 기본 활성화(True) —
    이 기능 도입 이전과 동일하게 전부 켜진 상태로 동작해야 기존 사용자 동작이
    안 바뀐다. 값이 '0'일 때만 off, 그 외(키 없음 포함)는 on."""
    placeholders = ",".join("?" * len(_CATEGORY_KEYS))
    rows = conn.execute(
        f"SELECT key, value FROM ai_settings WHERE key IN ({placeholders})",
        _CATEGORY_KEYS,
    ).fetchall()
    values = {row["key"]: row["value"] for row in rows}
    return {key: values.get(key, "1") != "0" for key in _CATEGORY_KEYS}


def run_scan(limit: int | None = None) -> dict:
    from ai_worker.pipeline import FacePipeline, analyze_and_store
    from ai_worker.tag_vocab import TAG_VOCAB
    from ai_worker.tagger import ClipTagger, ClipTaggingContext, tag_threshold_setting

    conn = db.connect()
    root = config.photo_root()
    flags = category_flags(conn)
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
        "photos": len(pending), "faces": 0, "errors": 0, "located": 0, "tagged": 0,
        "renamed": renamed, "orphaned": orphaned, "elapsed": 0.0,
    }

    # 폴더명 태깅(Kiwi)은 mtime 기반 pending과 무관한 커버리지 방식이라, 얼굴 재분석
    # 대상이 없어도(pending 비어도) 실행해야 한다 — 이 기능 도입 이전 사진이나
    # 경로복구로 새로 생긴 path 태그 공백을 여기서 채운다. 카테고리가 꺼져 있으면
    # 새로 생성하지 않는다(기존 태그는 그대로 둠).
    path_tagged = scanner.tag_paths_from_folder_names(conn) if flags["path_enabled"] else 0
    if path_tagged:
        log.info("폴더명 태깅(Kiwi): %d장에 path 태그 반영", path_tagged)
    summary["path_tagged"] = path_tagged

    if not pending:
        return summary

    pipeline = None
    enrollment = {}
    threshold = config.match_threshold()
    if flags["face_enabled"]:
        log.info("모델 로딩 중 (buffalo_l, det_size=%d)...", config.det_size())
        pipeline = FacePipeline()
        enrollment = matcher.load_enrollment(conn)
        log.info("등록 인물 %d명, threshold=%.2f", len(enrollment), threshold)
    else:
        log.info("얼굴 인식 비활성화(Admin 설정) — 이번 스캔은 얼굴 검출을 건너뜁니다")

    # CLIP 태깅은 얼굴 인식과 별개 기능이라, 모델 다운로드/로딩이 실패해도(네트워크
    # 불안정 등) 얼굴 분석 자체는 계속 진행한다 — best-effort.
    clip_ctx = None
    if flags["ai_tag_enabled"]:
        try:
            log.info("CLIP 태깅 모델 로딩 중...")
            clip_tagger = ClipTagger()
            tag_threshold = tag_threshold_setting(conn)
            text_embeds = clip_tagger.embed_texts([e["prompt"] for e in TAG_VOCAB])
            clip_ctx = ClipTaggingContext(
                tagger=clip_tagger, text_embeds=text_embeds, threshold=tag_threshold
            )
            log.info("CLIP 태깅 준비 완료 (어휘 %d개, threshold=%.2f)", len(TAG_VOCAB), tag_threshold)
        except Exception:
            log.exception("CLIP 태깅 모델 로딩 실패 — 이번 스캔은 사물(AI 태그) 태깅을 건너뜁니다")
    else:
        log.info("사물(AI 태그) 인식 비활성화(Admin 설정) — 이번 스캔은 CLIP 태깅을 건너뜁니다")

    start = time.monotonic()
    total_faces = 0
    errors = 0
    located = 0
    tagged = 0
    for i, (rel_path, mtime) in enumerate(pending, 1):
        face_count, ok, was_located, was_tagged = analyze_and_store(
            pipeline, conn, rel_path, mtime, enrollment, threshold,
            clip_ctx=clip_ctx, location_enabled=flags["location_enabled"],
        )
        total_faces += face_count
        if not ok:
            errors += 1
        if was_located:
            located += 1
        if was_tagged:
            tagged += 1
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
    summary["located"] = located
    summary["tagged"] = tagged
    summary["elapsed"] = elapsed
    return summary


def run_rematch() -> dict:
    conn = db.connect()
    count = matcher.rematch_all(conn, config.match_threshold())
    log.info("재매칭 완료: %d개 얼굴 매칭됨", count)
    return {"matched": count}


def run_tag_backfill(limit: int | None = None) -> dict:
    """AI 태그 재계산 — scan()의 pending_photos()(mtime 기반)와 달리
    photos_analyzed 전체(status='done')를 대상으로 하는 명시적 배치 작업.
    태그 어휘(tag_vocab.py)나 threshold를 바꾼 뒤, 또는 이 기능 도입 이전
    사진에 CLIP/위치를 소급 적용하고 싶을 때 admin이 의도적으로 실행한다.

    - photo_embeddings가 이미 있는 사진: 재인코딩 없이 캐시된 벡터로 재채점만
      (rescore_ai_tags_from_cache) — 어휘 확장의 핵심 이점.
    - photo_embeddings가 없는 사진: 새로 인코딩.
    - photo_locations가 없는 사진: GPS EXIF가 있으면 위치도 함께 채움.
    - 폴더명(Kiwi) 태깅은 이미 커버리지 방식이라(scanner.tag_paths_from_folder_names가
      매 scan에서 다룸) 별도 처리가 필요 없지만, scan을 한 번도 안 돌린 상태에서
      tag-backfill만 실행할 가능성을 대비해 여기서도 호출한다(idempotent).
    - status='error'(얼굴 분석 자체가 실패한) 사진은 대상에서 제외 — 같은 파일이라
      CLIP도 열지 못할 가능성이 높음.

    카테고리가 꺼져 있으면(Admin 설정) 해당 카테고리는 소급 처리도 건너뛴다 — "끄면
    새로 생성하지 않는다"는 원칙이 scan()뿐 아니라 backfill에도 동일하게 적용된다.
    반대로 껐다가 다시 켠 경우, 꺼져 있던 동안 건너뛴 사진은 정확히 이 함수가
    대상으로 삼는 "photo_embeddings/photo_locations가 없는 사진"과 일치하므로
    별도 로직 없이 이 배치를 한 번 더 돌리는 것만으로 밀린 부분이 채워진다.
    """
    from ai_worker import pipeline
    from ai_worker.tag_vocab import TAG_VOCAB
    from ai_worker.tagger import ClipTagger, ClipTaggingContext, tag_threshold_setting

    conn = db.connect()
    root = config.photo_root()
    flags = category_flags(conn)

    path_tagged = scanner.tag_paths_from_folder_names(conn) if flags["path_enabled"] else 0

    summary = {
        "photos": 0, "embedded": 0, "rescored": 0, "located": 0,
        "errors": 0, "path_tagged": path_tagged, "elapsed": 0.0,
    }

    if not flags["ai_tag_enabled"] and not flags["location_enabled"]:
        return summary

    rows = conn.execute(
        "SELECT path FROM photos_analyzed WHERE status = 'done' ORDER BY path"
    ).fetchall()
    targets = [r["path"] for r in rows]
    if limit is not None and len(targets) > limit:
        targets = random.Random(42).sample(targets, limit)
        log.info("--limit %d: 랜덤 샘플 %d장만 처리", limit, len(targets))
    summary["photos"] = len(targets)
    if not targets:
        return summary

    # scan()의 pending_photos()는 walk 결과가 0인데 과거 분석 이력이 있으면 마운트
    # 해제로 보고 건너뛴다. tag-backfill은 walk 없이 photos_analyzed를 그대로
    # 신뢰하므로, 같은 상황(root 마운트 해제)에서 대상 수천~수만 장 전부가
    # Image.open() 예외로 떨어져 로그를 뒤덮는 것을 막기 위해 동일한 보호를 둔다.
    if not os.path.isdir(root) or not os.listdir(root):
        log.warning("PHOTO_ROOT에 접근할 수 없습니다(root=%s) — 마운트 해제로 보고 "
                    "tag-backfill을 건너뜁니다.", root)
        return summary

    clip_ctx = None
    if flags["ai_tag_enabled"]:
        log.info("CLIP 태깅 모델 로딩 중...")
        clip_tagger = ClipTagger()
        threshold = tag_threshold_setting(conn)
        text_embeds = clip_tagger.embed_texts([e["prompt"] for e in TAG_VOCAB])
        clip_ctx = ClipTaggingContext(tagger=clip_tagger, text_embeds=text_embeds, threshold=threshold)
        log.info("CLIP 태깅 준비 완료 (어휘 %d개, threshold=%.2f)", len(TAG_VOCAB), threshold)

    start = time.monotonic()
    for i, rel_path in enumerate(targets, 1):
        has_embedding = conn.execute(
            "SELECT 1 FROM photo_embeddings WHERE photo_path = ?", (rel_path,)
        ).fetchone() is not None
        has_location = conn.execute(
            "SELECT 1 FROM photo_locations WHERE photo_path = ?", (rel_path,)
        ).fetchone() is not None
        need_embedding = flags["ai_tag_enabled"] and not has_embedding
        need_location = flags["location_enabled"] and not has_location

        # rescore_ai_tags_from_cache와 backfill_photo를 하나의 try로 묶는다 — 캐시된
        # 벡터가 손상된 경우(blob_to_embedding 실패 등) 한 장 때문에 전체 배치가
        # 죽지 않고, 사진 1장 = 1 트랜잭션(resumable) 원칙을 그대로 지킨다.
        try:
            if flags["ai_tag_enabled"] and has_embedding \
                    and pipeline.rescore_ai_tags_from_cache(conn, rel_path, clip_ctx):
                summary["rescored"] += 1
            if need_embedding or need_location:
                abs_path = os.path.join(root, rel_path)
                embedded, located = pipeline.backfill_photo(
                    conn, rel_path, abs_path, clip_ctx,
                    need_embedding=need_embedding, need_location=need_location,
                )
                summary["embedded"] += int(embedded)
                summary["located"] += int(located)
        except Exception:
            log.exception("%s 처리 실패 — 건너뜀", rel_path)
            summary["errors"] += 1
            conn.commit()
            continue

        conn.commit()
        if i % 200 == 0:
            elapsed = time.monotonic() - start
            log.info("%d/%d장 처리 (%.2f초/장)", i, len(targets), elapsed / i)

    summary["elapsed"] = time.monotonic() - start
    log.info(
        "tag-backfill 완료: %d장 (신규 임베딩 %d, 재채점 %d, 위치보완 %d), 에러 %d건, %.0f초",
        len(targets), summary["embedded"], summary["rescored"], summary["located"],
        summary["errors"], summary["elapsed"],
    )
    return summary


def run_review_ignored(target_person_id: int) -> None:
    conn = db.connect()
    count = matcher.match_ignored_for_person(conn, target_person_id, config.match_threshold())
    log.info("무시 얼굴 재검토 완료 (인물 #%d): 후보 %d개", target_person_id, count)


def main() -> None:
    parser = argparse.ArgumentParser(prog="ai_worker")
    parser.add_argument("command", choices=["scan", "rematch", "tag-backfill", "daemon"])
    parser.add_argument("--limit", type=int, default=None,
                        help="최대 처리 장수 (전체에서 균등 랜덤 샘플)")
    args = parser.parse_args()
    if args.command == "scan":
        run_scan(args.limit)
    elif args.command == "rematch":
        run_rematch()
    elif args.command == "tag-backfill":
        run_tag_backfill(args.limit)
    else:
        from ai_worker.daemon import run_daemon
        run_daemon()


if __name__ == "__main__":
    main()
