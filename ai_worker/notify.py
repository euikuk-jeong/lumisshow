"""Discord webhook 알림. AI_DISCORD_WEBHOOK_URL 미설정 시 조용히 스킵.

전송 실패(네트워크 오류 등)는 로그만 남기고 삼킨다 — 알림 실패로 daemon 루프가
죽으면 안 되기 때문."""

import json
import logging
import os
import time
import urllib.request

from ai_worker import config

log = logging.getLogger("ai_worker")

_MAX_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 2

# notify_scan_result 증분 판단용 직전 발송 상태. ai.db의 ai_settings 테이블은
# LumisShow 전용 쓰기 영역이라(ai_worker/CLAUDE.md 쓰기 주체 분리 규칙) 워커 내부
# 알림 상태는 DATA_DIR에 별도 파일로 둔다.
_STATE_FILENAME = "notify_state.json"


def _state_path() -> str:
    return os.path.join(config.data_dir(), _STATE_FILENAME)


def _load_last_pending() -> dict:
    try:
        with open(_state_path(), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError, OSError):
        return {}


def _save_last_pending(renamed: int, orphaned: int) -> None:
    try:
        os.makedirs(config.data_dir(), exist_ok=True)
        with open(_state_path(), "w", encoding="utf-8") as f:
            json.dump({"renamed": renamed, "orphaned": orphaned}, f)
    except OSError:
        log.exception("알림 상태 저장 실패")


def _admin_people_url() -> str:
    return f"{config.base_url()}/admin/people"


def notify_scan_result(summary: dict) -> None:
    """이번 스캔에서 실제로 처리한 게 없고(photos/path_tagged 둘 다 0) 경로 변경·
    삭제 승인 대기 누적 건수도 직전 발송 때와 그대로면 알림을 보내지 않는다 —
    매 스캔 무조건 발송하면 증분 없는 날도 매번 같은 pending 누적치가 와서 소음이
    됐음(2026-08-02 사용자 피드백). renamed/orphaned는 누적 카운트라 직전 발송값과
    비교해야 하고, 나머지는 이번 스캔에서 새로 처리된 건수만 보면 된다."""
    last = _load_last_pending()
    has_new_work = summary["photos"] > 0 or summary["path_tagged"] > 0
    pending_changed = (
        summary["renamed"] != last.get("renamed")
        or summary["orphaned"] != last.get("orphaned")
    )
    if not has_new_work and not pending_changed:
        return

    _send(
        "**LumisShow AI 스캔 완료**\n"
        f"사진 {summary['photos']}장 분석 (얼굴 {summary['faces']}개, "
        f"위치 {summary['located']}건, 태그 {summary['tagged']}건, "
        f"폴더명 태깅 {summary['path_tagged']}건, 에러 {summary['errors']}건)\n"
        f"경로 변경 승인 대기 {summary['renamed']}건, 삭제 승인 대기 {summary['orphaned']}건\n"
        f"소요 {summary['elapsed']:.0f}초\n"
        f"{_admin_people_url()}"
    )
    _save_last_pending(summary["renamed"], summary["orphaned"])


def notify_rematch_result(summary: dict) -> None:
    _send(
        f"**LumisShow AI 재매칭 완료**\n얼굴 {summary['matched']}개 매칭됨\n"
        f"{_admin_people_url()}"
    )


def notify_path_tag_reset_result(summary: dict) -> None:
    _send(
        "**LumisShow 폴더 태그 재계산 완료**\n"
        f"폴더명 태깅 {summary['path_tagged']}장\n"
        f"소요 {summary['elapsed']:.0f}초\n"
        f"{_admin_people_url()}"
    )


def notify_tag_backfill_result(summary: dict) -> None:
    _send(
        "**LumisShow AI 태그 재계산 완료**\n"
        f"사진 {summary['photos']}장 대상 (신규 임베딩 {summary['embedded']}장, "
        f"재채점 {summary['rescored']}장, 위치보완 {summary['located']}장, "
        f"에러 {summary['errors']}건)\n"
        f"폴더명 태깅 {summary['path_tagged']}장\n"
        f"소요 {summary['elapsed']:.0f}초\n"
        f"{_admin_people_url()}"
    )


def _send(content: str) -> None:
    url = config.discord_webhook_url()
    if not url:
        return
    body = json.dumps({"content": content}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "LumisShow-AI-Worker",  # 기본 UA는 Discord(Cloudflare)가 403으로 차단
        },
        method="POST",
    )
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            urllib.request.urlopen(req, timeout=10)
            return
        except Exception:
            if attempt == _MAX_ATTEMPTS:
                log.exception("Discord 알림 전송 실패 (%d회 시도)", attempt)
            else:
                log.warning("Discord 알림 전송 실패, %d초 후 재시도 (%d/%d)",
                            _RETRY_DELAY_SECONDS, attempt, _MAX_ATTEMPTS)
                time.sleep(_RETRY_DELAY_SECONDS)
