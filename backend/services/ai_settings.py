"""ai_settings(ai.db) 조회 — admin_people(설정 화면)·admin_browse(정보 패널/검색 카테고리 필터) 공용.

카테고리 플래그 키는 ai_worker/main.py의 category_flags()와 "1"/"0" 문자열 규약을
동일하게 맞춰야 한다(자동 동기화 테스트 없음, ai_worker/CLAUDE.md 참고).
"""

CATEGORY_SETTING_KEYS = ("face_enabled", "location_enabled", "path_enabled", "ai_tag_enabled")


async def read_ai_settings(db) -> dict:
    async with db.execute(
        "SELECT key, value FROM ai_settings WHERE key IN "
        "('scan_hour', 'tag_threshold', 'face_enabled', 'location_enabled', "
        "'path_enabled', 'ai_tag_enabled')"
    ) as cur:
        rows = await cur.fetchall()
    values = {row["key"]: row["value"] for row in rows}
    result = {
        "scan_hour": int(values["scan_hour"]) if "scan_hour" in values else None,
        "tag_threshold": float(values["tag_threshold"]) if "tag_threshold" in values else None,
    }
    # 카테고리 플래그는 키가 없으면 기본 활성화(true) — 이 기능 도입 이전과 동일하게
    # 전부 켜진 상태로 취급해야 기존 사용자 동작이 안 바뀐다.
    for key in CATEGORY_SETTING_KEYS:
        result[key] = values.get(key, "1") != "0"
    return result
