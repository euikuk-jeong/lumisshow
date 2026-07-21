"""데몬 모드 (M2): 야간 자동 스캔 + jobs 큐 폴링.

- 매일 스캔 시각(ai_settings.scan_hour 우선, 없으면 AI_SCAN_HOUR, 기본 02:00,
  로컬 TZ)에 증분 스캔 자동 실행 — Admin 설정 변경은 다음 폴링 루프에 반영
- LumisShow Admin이 jobs 테이블에 넣은 수동 트리거(scan/rematch)를
  AI_POLL_INTERVAL(기본 30초) 간격으로 폴링·소비 (status만 워커가 갱신)
"""

import logging
import sqlite3
import time
from datetime import datetime, timedelta

from ai_worker import config, db

log = logging.getLogger("ai_worker")


def next_scan_time(now: datetime, hour: int) -> datetime:
    """now 이후 가장 가까운 '오늘/내일 hour시 정각'을 반환."""
    nxt = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(days=1)
    return nxt


def scan_hour_setting(conn: sqlite3.Connection) -> int:
    """ai_settings의 scan_hour(Admin 설정)가 있으면 우선, 없으면 환경변수."""
    row = conn.execute(
        "SELECT value FROM ai_settings WHERE key = 'scan_hour'"
    ).fetchone()
    if row is not None:
        try:
            hour = int(row["value"])
            if 0 <= hour <= 23:
                return hour
        except ValueError:
            pass
    return config.scan_hour()


def reset_stale_jobs(conn: sqlite3.Connection) -> int:
    """이전 실행이 비정상 종료해 'running'으로 남은 잡을 pending으로 복구."""
    cur = conn.execute("UPDATE jobs SET status='pending' WHERE status='running'")
    conn.commit()
    return cur.rowcount


def claim_next_job(conn: sqlite3.Connection) -> tuple[int, str, int | None] | None:
    """가장 오래된 pending 잡을 running으로 전환하고 (id, type, target_person_id) 반환."""
    row = conn.execute(
        "SELECT id, type, target_person_id FROM jobs WHERE status='pending' ORDER BY id LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    conn.execute("UPDATE jobs SET status='running' WHERE id=?", (row["id"],))
    conn.commit()
    return row["id"], row["type"], row["target_person_id"]


def finish_job(conn: sqlite3.Connection, job_id: int, status: str) -> None:
    conn.execute(
        "UPDATE jobs SET status=?, finished_at=CURRENT_TIMESTAMP WHERE id=?",
        (status, job_id),
    )
    conn.commit()


def run_daemon() -> None:
    from ai_worker.main import run_rematch, run_review_ignored, run_scan  # 순환 import 방지용 lazy

    conn = db.connect()
    stale = reset_stale_jobs(conn)
    if stale:
        log.info("비정상 종료된 running 잡 %d개를 pending으로 복구", stale)

    hour = scan_hour_setting(conn)
    nxt = next_scan_time(datetime.now(), hour)
    log.info("데몬 시작: 다음 자동 스캔 %s, 폴링 %d초", nxt, config.poll_interval())

    while True:
        new_hour = scan_hour_setting(conn)
        if new_hour != hour:
            hour = new_hour
            nxt = next_scan_time(datetime.now(), hour)
            log.info("스캔 시각 변경 감지: %d시 → 다음 자동 스캔 %s", hour, nxt)

        job = claim_next_job(conn)
        if job is not None:
            job_id, job_type, target_person_id = job
            log.info("잡 #%d (%s) 실행", job_id, job_type)
            try:
                if job_type == "scan":
                    run_scan()
                elif job_type == "rematch":
                    run_rematch()
                elif job_type == "review_ignored":
                    run_review_ignored(target_person_id)
                else:
                    raise ValueError(f"알 수 없는 잡 타입: {job_type}")
                finish_job(conn, job_id, "done")
            except Exception:
                log.exception("잡 #%d 실패", job_id)
                finish_job(conn, job_id, "error")
            continue  # 잡 처리 직후엔 대기 없이 다음 잡 확인

        if datetime.now() >= nxt:
            log.info("야간 자동 스캔 시작")
            try:
                run_scan()
            except Exception:
                log.exception("자동 스캔 실패 — 다음 주기에 재시도")
            nxt = next_scan_time(datetime.now(), hour)
            log.info("다음 자동 스캔: %s", nxt)
            continue

        time.sleep(config.poll_interval())
