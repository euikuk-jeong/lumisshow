"""photo_tags 일괄 조회 — 정보 패널(i 버튼) 태그 노출(Phase 6)용.

admin_people.py(Admin 슬라이드쇼)·share.py(공유 링크 슬라이드쇼)가 각자 뷰어에
맞는 source만 골라 조회한다. photo_meta.py의 load_photo_meta()와 동일하게
IN 절 일괄 조회로 N+1을 피한다.
"""

# doc/tagging_requirement.md "정보 패널(i 버튼) 태그 노출" 절의 노출 범위 표 —
# location/person은 Admin 전용(오매칭·프라이버시 이슈로 얼굴 인식 자체가 승인
# 큐를 거치는 것과 동일한 이유로 공유 링크에는 노출하지 않는다).
ADMIN_INFO_PANEL_SOURCES = ("person", "location", "ai", "path", "manual")
SHARE_INFO_PANEL_SOURCES = ("ai", "path", "manual")

_CHUNK = 400  # SQLite 파라미터 한도(999) 대비 여유 — sources(최대 5개) 파라미터도 매 청크마다 함께 바인딩됨


async def load_photo_tags(
    paths: list[str], db, sources: tuple[str, ...]
) -> dict[str, dict[str, list[str]]]:
    """{photo_path: {source: [tag, ...]}} — paths/sources에 없는 조합은 빈 리스트.

    각 리스트는 id(삽입 순서) 기준으로 정렬한다 — tag 알파벳순이면 location의
    city/country가 SQLite 기본 collation(UTF-8 바이트 순)에 따라 뒤섞여 "대한민국,
    서울"처럼 국가가 먼저 나올 수 있는데, ai_worker/geocoder.py의
    sync_location_tag()가 city를 country보다 먼저 INSERT하므로 삽입 순서를 쓰면
    doc/tagging_requirement.md 예시("서울, 대한민국")와 항상 일치한다. ai/path/
    manual/person은 의미 있는 순서가 없어 어느 쪽이든 상관없다."""
    result: dict[str, dict[str, list[str]]] = {p: {s: [] for s in sources} for p in paths}
    if not paths or not sources:
        return result

    src_placeholders = ",".join("?" * len(sources))
    for i in range(0, len(paths), _CHUNK):
        chunk = paths[i:i + _CHUNK]
        placeholders = ",".join("?" * len(chunk))
        async with db.execute(
            f"""SELECT photo_path, tag, source FROM photo_tags
                WHERE source IN ({src_placeholders}) AND photo_path IN ({placeholders})
                ORDER BY photo_path, id""",
            (*sources, *chunk),
        ) as cur:
            for row in await cur.fetchall():
                result[row["photo_path"]][row["source"]].append(row["tag"])
    return result


# ai_settings 카테고리 플래그 키(services/ai_settings.py.CATEGORY_SETTING_KEYS와 값은 같으나
# photo_tags.source 이름으로 변환된 버전) → source 매핑. manual은 토글이 없어
# 항상 검색/노출 대상.
_CATEGORY_TO_SOURCE = {
    "face_enabled": "person",
    "location_enabled": "location",
    "path_enabled": "path",
    "ai_tag_enabled": "ai",
}


def enabled_sources(category_flags: dict) -> tuple[str, ...]:
    """{"face_enabled": bool, ...} → 꺼진 카테고리를 제외한 source 튜플(manual 포함).

    photo-info(정보 패널)·검색 양쪽이 "꺼진 카테고리는 기존 DB에 있어도 미표시"
    원칙을 공유하도록 하나로 모은 헬퍼."""
    return ("manual",) + tuple(
        source for key, source in _CATEGORY_TO_SOURCE.items() if category_flags.get(key, True)
    )


async def search_tag_matched_paths(query: str, db, sources: tuple[str, ...]) -> set[str]:
    """query를 부분 문자열로 포함하는 tag가 있는 photo_path 집합(sources로 한정) —
    Admin 사진 탐색 검색(admin_browse.py)이 파일명 검색과 OR로 합쳐 쓴다.
    원래는 source 구분 없이 전체가 대상이었으나(검색은 정보 패널과 달리 노출 범위
    통제가 필요 없는 Admin 전용 화면이라는 이유), 카테고리 off 시 "기존 DB에
    있어도 검색에서 제외" 요구사항 추가로 enabled_sources() 결과를 받아 필터한다."""
    if not sources:
        return set()
    like = "%" + query.translate(str.maketrans({"\\": "\\\\", "%": "\\%", "_": "\\_"})) + "%"
    placeholders = ",".join("?" * len(sources))
    async with db.execute(
        f"SELECT DISTINCT photo_path FROM photo_tags WHERE tag LIKE ? ESCAPE '\\' "
        f"AND source IN ({placeholders})",
        (like, *sources),
    ) as cur:
        return {r["photo_path"] for r in await cur.fetchall()}
