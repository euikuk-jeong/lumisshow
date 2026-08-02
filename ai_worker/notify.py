"""Discord webhook 알림. AI_DISCORD_WEBHOOK_URL 미설정 시 조용히 스킵.

전송 실패(네트워크 오류 등)는 로그만 남기고 삼킨다 — 알림 실패로 daemon 루프가
죽으면 안 되기 때문."""

import json
import logging
import time
import urllib.request

from ai_worker import config

log = logging.getLogger("ai_worker")

_MAX_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 2


def _admin_people_url() -> str:
    return f"{config.base_url()}/admin/people"


def notify_scan_result(summary: dict) -> None:
    _send(
        "**LumisShow AI 스캔 완료**\n"
        f"사진 {summary['photos']}장 분석 (얼굴 {summary['faces']}개, "
        f"에러 {summary['errors']}건)\n"
        f"경로 변경 승인 대기 {summary['renamed']}건, 삭제 승인 대기 {summary['orphaned']}건\n"
        f"소요 {summary['elapsed']:.0f}초\n"
        f"{_admin_people_url()}"
    )


def notify_rematch_result(summary: dict) -> None:
    _send(
        f"**LumisShow AI 재매칭 완료**\n얼굴 {summary['matched']}개 매칭됨\n"
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
