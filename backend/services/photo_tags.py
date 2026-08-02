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


async def search_tag_matched_paths(query: str, db) -> set[str]:
    """query를 부분 문자열로 포함하는 tag가 있는 photo_path 집합(source 구분 없이
    전부) — Admin 사진 탐색 검색(admin_browse.py)이 파일명 검색과 OR로 합쳐 쓴다.
    source를 안 가리는 이유: 검색은 노출 범위 통제가 필요한 화면(정보 패널)이
    아니라 Admin 본인만 보는 탐색기이므로, person(확정 인물명)·location까지 전부
    검색 대상이어야 유용하다."""
    like = "%" + query.translate(str.maketrans({"\\": "\\\\", "%": "\\%", "_": "\\_"})) + "%"
    async with db.execute(
        "SELECT DISTINCT photo_path FROM photo_tags WHERE tag LIKE ? ESCAPE '\\'",
        (like,),
    ) as cur:
        return {r["photo_path"] for r in await cur.fetchall()}
