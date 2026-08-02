"""XMP 사이드카 export — DB(photo_tags/photo_locations/faces+face_labels)에만 있는
메타데이터를 다른 사진 관리 툴(Lightroom·digiKam 등)이 읽을 수 있는 XMP로 직렬화한다.

원본 사진은 절대 수정하지 않는다(PHOTO_ROOT 읽기 전용 마운트 원칙) — export는
photo_path 기준으로 새 .xmp 텍스트를 생성해 ZIP으로 스트리밍할 뿐, 디스크에
아무것도 쓰지 않는다. 매핑은 doc/tagging_requirement.md "XMP 참고 매핑"을 따른다:
  dc:subject                    ← photo_tags (전체 source)
  mwg-rs:RegionList             ← faces + face_labels (확정 인물만, 추정 매칭 제외)
  Iptc4xmpExt:LocationCreated   ← photo_locations
"""

import json
from xml.sax.saxutils import escape as _esc

# XMP export는 정보 패널(services/photo_tags.py)과 달리 뷰어별 프라이버시 구분이
# 없다 — Admin 본인이 다운로드하는 개인 백업/이전용 파일이라 source 전부를 포함한다.
XMP_EXPORT_TAG_SOURCES = ("ai", "manual", "path", "location", "person")

_CHUNK = 400  # photo_tags.py/photo_meta.py와 동일한 SQLite 파라미터 한도 대비 청크 크기


async def load_locations(paths: list[str], db) -> dict[str, dict]:
    """{photo_path: {"city": str|None, "country": str|None}} — photo_locations 일괄 조회."""
    result: dict[str, dict] = {}
    if not paths:
        return result
    for i in range(0, len(paths), _CHUNK):
        chunk = paths[i:i + _CHUNK]
        placeholders = ",".join("?" * len(chunk))
        async with db.execute(
            f"SELECT photo_path, city, country FROM photo_locations WHERE photo_path IN ({placeholders})",
            chunk,
        ) as cur:
            for row in await cur.fetchall():
                result[row["photo_path"]] = {"city": row["city"], "country": row["country"]}
    return result


async def load_confirmed_regions(paths: list[str], db) -> dict[str, list[dict]]:
    """{photo_path: [{"name": str, "x1":.., "y1":.., "x2":.., "y2":..}, ...]}

    face_labels로 확정된 얼굴만 대상 — face_matches(AI 추정, 미확정)는 제외한다.
    사물/장면 태그와 달리 사람 이름은 오매칭·프라이버시 문제로 얼굴 인식 자체가
    승인 큐를 거치므로(person 태그 동기화와 동일 원칙), 아직 사람이 확인 안 한
    추정치를 외부 툴로 내보내면 그 취지와 충돌한다."""
    result: dict[str, list[dict]] = {}
    if not paths:
        return result
    for i in range(0, len(paths), _CHUNK):
        chunk = paths[i:i + _CHUNK]
        placeholders = ",".join("?" * len(chunk))
        async with db.execute(
            f"""SELECT f.photo_path, f.bbox, p.name FROM faces f
                JOIN face_labels fl ON fl.face_id = f.id
                JOIN persons p ON p.id = fl.person_id
                WHERE f.photo_path IN ({placeholders})""",
            chunk,
        ) as cur:
            for row in await cur.fetchall():
                x1, y1, x2, y2 = json.loads(row["bbox"])
                result.setdefault(row["photo_path"], []).append(
                    {"name": row["name"], "x1": x1, "y1": y1, "x2": x2, "y2": y2}
                )
    return result


def has_exportable_content(
    tags: list[str],
    regions: list[dict],
    location: dict | None,
    width: int | None,
    height: int | None,
) -> bool:
    """build_xmp_content()가 None이 아닌 결과를 낼지 미리 판단(문자열을 만들지 않고
    bool 연산만 함) — 라우터가 45,000장 전체를 한 번에 큐잉하기 전에 대상에서 제외할
    사진을 값싸게 걸러내는 데 쓴다(XMP 텍스트를 다 만든 뒤 버리는 건 낭비)."""
    has_regions = bool(regions) and bool(width) and bool(height)
    has_location = bool(location) and bool(location.get("city") or location.get("country"))
    return bool(tags) or has_regions or has_location


def build_xmp_content(
    tags: list[str],
    regions: list[dict],
    location: dict | None,
    width: int | None,
    height: int | None,
) -> str | None:
    """사진 1장분의 XMP 사이드카 XML 텍스트. 내보낼 내용이 하나도 없으면 None
    (호출자는 이 경우 해당 사진의 .xmp 자체를 만들지 않는다).

    mwg-rs:RegionList는 width/height(픽셀)가 있어야 bbox를 0~1 비율로 정규화할 수
    있다 — EXIF 읽기 실패 등으로 크기를 모르면 얼굴 영역이 있어도 통째로 생략한다
    (잘못된 비율보다 생략이 안전)."""
    has_regions = bool(regions) and width and height
    has_location = bool(location) and (location.get("city") or location.get("country"))
    if not has_exportable_content(tags, regions, location, width, height):
        return None

    # xpacket 시작 태그의 begin 속성 값은 리터럴 BOM(U+FEFF) 한 글자 — XMP 스펙 요구사항.
    # 소스 파일에 보이지 않는 글자를 직접 넣으면 리뷰·편집 중 사고 나기 쉬워 chr(0xFEFF)로 명시적으로 생성.
    xpacket_begin = '<?xpacket begin="' + chr(0xFEFF) + '" id="W5M0MpCehiHzreSzNTczkc9d"?>'
    lines = [
        xpacket_begin,
        '<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="LumisShow">',
        ' <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">',
        '  <rdf:Description rdf:about=""',
        '    xmlns:dc="http://purl.org/dc/elements/1.1/"',
        '    xmlns:mwg-rs="http://www.metadataworkinggroup.com/schemas/regions/"',
        '    xmlns:stArea="http://ns.adobe.com/xmp/sType/Area#"',
        '    xmlns:stDim="http://ns.adobe.com/xap/1.0/sType/Dimensions#"',
        '    xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/">',
    ]

    if tags:
        lines.append('   <dc:subject>')
        lines.append('    <rdf:Bag>')
        for t in tags:
            lines.append(f'     <rdf:li>{_esc(t)}</rdf:li>')
        lines.append('    </rdf:Bag>')
        lines.append('   </dc:subject>')

    if has_regions:
        lines.append('   <mwg-rs:Regions rdf:parseType="Resource">')
        lines.append(f'    <mwg-rs:AppliedToDimensions stDim:w="{width}" stDim:h="{height}" stDim:unit="pixel"/>')
        lines.append('    <mwg-rs:RegionList>')
        lines.append('     <rdf:Bag>')
        for r in regions:
            cx = (r["x1"] + r["x2"]) / 2 / width
            cy = (r["y1"] + r["y2"]) / 2 / height
            rw = (r["x2"] - r["x1"]) / width
            rh = (r["y2"] - r["y1"]) / height
            lines.append('      <rdf:li rdf:parseType="Resource">')
            lines.append(f'       <mwg-rs:Name>{_esc(r["name"])}</mwg-rs:Name>')
            lines.append('       <mwg-rs:Type>Face</mwg-rs:Type>')
            lines.append(
                f'       <mwg-rs:Area stArea:x="{cx:.6f}" stArea:y="{cy:.6f}" '
                f'stArea:w="{rw:.6f}" stArea:h="{rh:.6f}" stArea:unit="normalized"/>'
            )
            lines.append('      </rdf:li>')
        lines.append('     </rdf:Bag>')
        lines.append('    </mwg-rs:RegionList>')
        lines.append('   </mwg-rs:Regions>')

    if has_location:
        lines.append('   <Iptc4xmpExt:LocationCreated rdf:parseType="Resource">')
        if location.get("city"):
            lines.append(f'    <Iptc4xmpExt:City>{_esc(location["city"])}</Iptc4xmpExt:City>')
        if location.get("country"):
            lines.append(f'    <Iptc4xmpExt:CountryName>{_esc(location["country"])}</Iptc4xmpExt:CountryName>')
        lines.append('   </Iptc4xmpExt:LocationCreated>')

    lines += [
        '  </rdf:Description>',
        ' </rdf:RDF>',
        '</x:xmpmeta>',
        '<?xpacket end="w"?>',
    ]
    return '\n'.join(lines) + '\n'


def xmp_bytes_iter(
    tags: list[str],
    regions: list[dict],
    location: dict | None,
    width: int | None,
    height: int | None,
):
    """build_xmp_content()를 실제 소비 시점까지 지연 실행하는 제너레이터.

    zipstream-ng의 add()는 문자열/바이트를 그대로 넘기면 인코딩 시점까지 메모리에
    들고 있는다(라이브러리 규모의 export에서 텍스트를 전부 미리 만들어 items에
    쌓아두면 그만큼 한꺼번에 메모리를 차지한다) — iterator 프로토콜을 만족하는
    객체를 넘기면 실제 ZIP 인코딩(스트리밍, 한 항목씩) 시점까지 본문 생성을 미룰
    수 있어 대상이 사진 전체일 수 있는 XMP export에는 이 지연 방식이 필요하다."""
    xmp = build_xmp_content(tags, regions, location, width, height)
    if xmp is not None:
        yield xmp.encode("utf-8")
