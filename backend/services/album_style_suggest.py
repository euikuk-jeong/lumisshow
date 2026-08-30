"""앨범 이름/설명 → 배경음악·테마·타이틀 폰트 LLM 추천.

doc/todo/todo.md(2026-08-24 grilling으로 설계 확정)의 프라이버시 전제: 사진 원본·EXIF·
태그는 절대 LLM에 보내지 않는다 — 앨범 이름+설명 텍스트만 프롬프트에 포함한다.
"""

import os
from typing import Optional

from backend.services.album_style_vocab import BUNDLED_MUSIC_CREDITS, THEME_OPTIONS, TITLE_FONT_OPTIONS
from backend.services.llm_client import LlmError, call_llm, extract_json

_PROMPT_TEMPLATE = """사진 슬라이드쇼 앨범에 어울리는 배경음악·테마·타이틀 폰트를 추천해주세요.

앨범 이름: {name}
설명: {description}

# 배경음악 후보 (id 중 하나만 선택)
{music_lines}

# 테마 후보 (id 중 하나만 선택)
{theme_lines}

# 타이틀 폰트 후보 (id 중 하나만 선택)
{font_lines}

아래 JSON 형식으로만 답하세요. 다른 설명·마크다운은 붙이지 마세요.
{{"music_id": "...", "theme_id": "...", "font_id": "...", "reason": "한 줄 추천 사유(한국어, 40자 이내)"}}
"""


def _build_prompt(name: str, description: Optional[str]) -> str:
    music_lines = "\n".join(
        f'- id="{t["file"]}": 무드={t["mood"]}, 곡명={t["title"]}' for t in BUNDLED_MUSIC_CREDITS
    )
    theme_lines = "\n".join(f'- id="{t["id"]}": {t["label"]}' for t in THEME_OPTIONS)
    font_lines = "\n".join(f'- id="{t["id"]}": {t["label"]} — {t["note"]}' for t in TITLE_FONT_OPTIONS)
    return _PROMPT_TEMPLATE.format(
        name=name,
        description=description or "(없음)",
        music_lines=music_lines,
        theme_lines=theme_lines,
        font_lines=font_lines,
    )


def suggest_style(config: dict, name: str, description: Optional[str], data_dir: str) -> dict:
    """동기 함수 — 호출부가 run_in_threadpool로 감싼다.

    파싱 완전 실패(JSON 자체를 못 찾음)는 LlmError를 던져 호출자가 에러 메시지만
    보여주게 한다(자동 재시도 없음). 후보 목록에 없는 값은 그 필드만 None으로
    무시하는 부분 적용을 허용한다 — 마찬가지로 자동 재시도하지 않는다.
    """
    prompt = _build_prompt(name, description)
    raw_text = call_llm(config, prompt)
    parsed = extract_json(raw_text)
    if parsed is None:
        raise LlmError("AI 응답을 해석하지 못했습니다")

    music_ids = {t["file"] for t in BUNDLED_MUSIC_CREDITS}
    theme_ids = {t["id"] for t in THEME_OPTIONS}
    font_ids = {t["id"] for t in TITLE_FONT_OPTIONS}

    music_id = parsed.get("music_id")
    theme_id = parsed.get("theme_id")
    font_id = parsed.get("font_id")
    reason = parsed.get("reason")

    music_path = None
    if isinstance(music_id, str) and music_id in music_ids:
        candidate = os.path.join(data_dir, "music", "bundled", music_id)
        if os.path.isfile(candidate):
            music_path = candidate

    return {
        "music_path": music_path,
        "ui_theme": theme_id if isinstance(theme_id, str) and theme_id in theme_ids else None,
        "title_font": font_id if isinstance(font_id, str) and font_id in font_ids else None,
        "reason": str(reason)[:200] if reason else "",
    }
