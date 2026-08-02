"""backend/services/xmp_export.py + GET /api/admin/tags/xmp-export 테스트."""

import io
import zipfile
from xml.etree import ElementTree

import aiosqlite

from backend.services.xmp_export import (
    build_xmp_content,
    has_exportable_content,
    load_confirmed_regions,
    load_locations,
    xmp_bytes_iter,
)


# ── build_xmp_content ────────────────────────────────────────────────────


def test_build_xmp_content_returns_none_when_nothing_to_export():
    assert build_xmp_content([], [], None, None, None) is None
    assert build_xmp_content([], [], {"city": None, "country": None}, None, None) is None


def test_build_xmp_content_includes_dc_subject_tags_escaped():
    xmp = build_xmp_content(["캠핑", "R&D <lab>"], [], None, None, None)
    assert "<rdf:li>캠핑</rdf:li>" in xmp
    assert "<rdf:li>R&amp;D &lt;lab&gt;</rdf:li>" in xmp


def test_build_xmp_content_computes_normalized_region_area():
    regions = [{"name": "홍길동", "x1": 100.0, "y1": 200.0, "x2": 300.0, "y2": 600.0}]
    xmp = build_xmp_content([], regions, None, width=1000, height=1000)
    # center=(200,400)/1000=(0.2,0.4), w=(300-100)/1000=0.2, h=(600-200)/1000=0.4
    assert 'stArea:x="0.200000"' in xmp
    assert 'stArea:y="0.400000"' in xmp
    assert 'stArea:w="0.200000"' in xmp
    assert 'stArea:h="0.400000"' in xmp
    assert "<mwg-rs:Name>홍길동</mwg-rs:Name>" in xmp
    assert 'stDim:w="1000" stDim:h="1000"' in xmp


def test_build_xmp_content_skips_regions_without_dimensions():
    """width/height를 모르면 얼굴 영역이 있어도 mwg-rs:Regions 자체를 생략한다 —
    잘못된 비율을 내보내는 것보다 생략이 안전(모듈 docstring 참고)."""
    regions = [{"name": "홍길동", "x1": 0, "y1": 0, "x2": 10, "y2": 10}]
    xmp = build_xmp_content([], regions, None, width=None, height=None)
    assert xmp is None  # 태그/위치도 없으면 아예 파일을 안 만듦

    xmp = build_xmp_content(["캠핑"], regions, None, width=None, height=None)
    assert "mwg-rs:Regions" not in xmp
    assert "캠핑" in xmp


def test_build_xmp_content_includes_location_city_and_country():
    xmp = build_xmp_content([], [], {"city": "서울", "country": "대한민국"}, None, None)
    assert "<Iptc4xmpExt:City>서울</Iptc4xmpExt:City>" in xmp
    assert "<Iptc4xmpExt:CountryName>대한민국</Iptc4xmpExt:CountryName>" in xmp


def test_build_xmp_content_location_partial_city_only():
    xmp = build_xmp_content([], [], {"city": "서울", "country": None}, None, None)
    assert "<Iptc4xmpExt:City>서울</Iptc4xmpExt:City>" in xmp
    assert "CountryName" not in xmp


def test_build_xmp_content_is_well_formed_xml():
    regions = [{"name": "홍길동", "x1": 0, "y1": 0, "x2": 10, "y2": 10}]
    xmp = build_xmp_content(
        ["캠핑", "바다"], regions, {"city": "서울", "country": "대한민국"}, width=100, height=100
    )
    # <?xpacket ...?>는 XML 처리 명령어로 유효 — BOM이 포함된 첫 줄만 벗겨내고 파싱
    body = xmp.split("\n", 1)[1]
    root = ElementTree.fromstring(body.encode("utf-8"))
    assert root.tag.endswith("xmpmeta")


# ── has_exportable_content / xmp_bytes_iter ──────────────────────────────


def test_has_exportable_content_matches_build_xmp_content_none_cases():
    """build_xmp_content()가 None을 반환하는 입력은 has_exportable_content()도
    False여야 한다 — 라우터가 이 값으로 큐잉 전 필터링을 하므로 둘이 어긋나면
    안 만들어야 할 항목이 0바이트 파일로 ZIP에 들어갈 수 있다."""
    assert has_exportable_content([], [], None, None, None) is False
    assert has_exportable_content([], [], {"city": None, "country": None}, None, None) is False
    assert has_exportable_content([], [{"name": "x", "x1": 0, "y1": 0, "x2": 1, "y2": 1}], None, None, None) is False
    assert has_exportable_content(["캠핑"], [], None, None, None) is True


def test_xmp_bytes_iter_defers_content_generation_until_consumed():
    """xmp_bytes_iter()는 호출 즉시 build_xmp_content()를 실행하지 않는 제너레이터를
    반환한다 — 실제로 next()/for로 소비할 때만 본문이 만들어진다(대량 export에서
    ZIP 인코딩 시점까지 메모리에 문자열을 쌓아두지 않기 위한 지연 실행)."""
    gen = xmp_bytes_iter(["캠핑"], [], None, None, None)
    import inspect

    assert inspect.isgenerator(gen)
    chunks = list(gen)
    assert len(chunks) == 1
    assert isinstance(chunks[0], bytes)
    assert "캠핑".encode("utf-8") in chunks[0]

    # 내보낼 게 없으면 아무 것도 yield하지 않는다(빈 파일이 아니라 항목 자체가 없어야
    # 하므로, 호출자는 has_exportable_content()로 이 경우를 사전에 걸러 애초에
    # items에 넣지 않아야 함 — 이 제너레이터 자체는 그저 빈 iterator가 됨).
    empty_gen = xmp_bytes_iter([], [], None, None, None)
    assert list(empty_gen) == []


# ── load_locations / load_confirmed_regions ──────────────────────────────


async def _ai_conn():
    from backend.models.ai_database import _ai_db_path

    conn = await aiosqlite.connect(_ai_db_path())
    conn.row_factory = aiosqlite.Row
    return conn


async def test_load_locations_bulk_query(client):
    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        await db.execute(
            "INSERT INTO photo_locations (photo_path, city, country) VALUES "
            "('2024/a.jpg', '서울', '대한민국'), ('2024/b.jpg', NULL, '일본')"
        )
        await db.commit()

    db = await _ai_conn()
    try:
        result = await load_locations(["2024/a.jpg", "2024/b.jpg", "2024/c.jpg"], db)
    finally:
        await db.close()
    assert result["2024/a.jpg"] == {"city": "서울", "country": "대한민국"}
    assert result["2024/b.jpg"] == {"city": None, "country": "일본"}
    assert "2024/c.jpg" not in result


async def test_load_confirmed_regions_only_includes_confirmed_labels(client):
    """face_matches만 있는(사람이 확인 안 한 AI 추정) 얼굴과, person_id가 NULL인
    라벨('등록 인물 아님'으로 무시 처리)은 제외돼야 한다 — 얼굴 인식 승인 큐 취지."""
    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        await db.execute("INSERT INTO persons (name) VALUES ('지우')")
        cur = await db.execute("SELECT id FROM persons WHERE name = '지우'")
        person_id = (await cur.fetchone())[0]

        # 확정 라벨 — 포함돼야 함
        cur = await db.execute(
            "INSERT INTO faces (photo_path, bbox, det_score, embedding) VALUES (?, ?, ?, ?)",
            ("2024/a.jpg", "[10.0, 20.0, 30.0, 40.0]", 0.9, b"\x00" * 8),
        )
        face_a = cur.lastrowid
        await db.execute(
            "INSERT INTO face_labels (face_id, person_id) VALUES (?, ?)", (face_a, person_id)
        )

        # AI 추정만(미확정) — 제외돼야 함
        cur = await db.execute(
            "INSERT INTO faces (photo_path, bbox, det_score, embedding) VALUES (?, ?, ?, ?)",
            ("2024/b.jpg", "[0,0,10,10]", 0.9, b"\x00" * 8),
        )
        face_b = cur.lastrowid
        await db.execute(
            "INSERT INTO face_matches (face_id, person_id, score) VALUES (?, ?, ?)",
            (face_b, person_id, 0.8),
        )

        # '무시' 처리(person_id NULL) — 제외돼야 함
        cur = await db.execute(
            "INSERT INTO faces (photo_path, bbox, det_score, embedding) VALUES (?, ?, ?, ?)",
            ("2024/c.jpg", "[0,0,10,10]", 0.9, b"\x00" * 8),
        )
        face_c = cur.lastrowid
        await db.execute(
            "INSERT INTO face_labels (face_id, person_id) VALUES (?, NULL)", (face_c,)
        )
        await db.commit()

    db = await _ai_conn()
    try:
        result = await load_confirmed_regions(["2024/a.jpg", "2024/b.jpg", "2024/c.jpg"], db)
    finally:
        await db.close()

    assert result == {
        "2024/a.jpg": [{"name": "지우", "x1": 10.0, "y1": 20.0, "x2": 30.0, "y2": 40.0}]
    }


async def test_load_confirmed_regions_empty_paths_returns_empty_dict(client):
    db = await _ai_conn()
    try:
        result = await load_confirmed_regions([], db)
    finally:
        await db.close()
    assert result == {}


# ── GET /api/admin/tags/xmp-export ───────────────────────────────────────


async def _seed_meta(file_path: str, width: int = 1000, height: int = 800) -> None:
    from backend.models.database import _db_path, _PHOTO_META_CACHE_VERSION

    async with aiosqlite.connect(_db_path()) as db:
        await db.execute(
            "INSERT INTO photo_meta_cache (file_path, width, height, cache_version) VALUES (?, ?, ?, ?)",
            (file_path, width, height, _PHOTO_META_CACHE_VERSION),
        )
        await db.commit()


def _read_zip(content: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(content))


async def test_export_xmp_requires_auth(client):
    r = await client.get("/api/admin/tags/xmp-export")
    assert r.status_code == 401


async def test_export_xmp_empty_when_nothing_to_export(admin_client):
    r = await admin_client.get("/api/admin/tags/xmp-export")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert "attachment" in r.headers["content-disposition"]
    zf = _read_zip(r.content)
    assert zf.namelist() == []


async def test_export_xmp_returns_zip_with_expected_entries(admin_client):
    from backend.models.ai_database import _ai_db_path

    await _seed_meta("2025/여름휴가/photo_0.jpg")
    async with aiosqlite.connect(_ai_db_path()) as db:
        await db.execute(
            "INSERT INTO photo_tags (photo_path, tag, source) VALUES "
            "('2025/여름휴가/photo_0.jpg', '캠핑', 'ai')"
        )
        await db.execute(
            "INSERT INTO photo_locations (photo_path, city, country) VALUES "
            "('2025/여름휴가/photo_0.jpg', '서울', '대한민국')"
        )
        await db.commit()

    r = await admin_client.get("/api/admin/tags/xmp-export")
    assert r.status_code == 200
    zf = _read_zip(r.content)
    # 원본과 동일한 상대 폴더 구조 + 확장자만 .xmp로 교체
    assert zf.namelist() == ["2025/여름휴가/photo_0.xmp"]
    content = zf.read("2025/여름휴가/photo_0.xmp").decode("utf-8")
    assert "캠핑" in content
    assert "서울" in content
    assert "대한민국" in content


async def test_export_xmp_excludes_photos_with_no_exportable_data(admin_client):
    """faces 행이 있어도 확정 라벨이 없으면(AI 추정만) 내보낼 게 없어 파일 자체가
    ZIP에 안 들어가야 한다."""
    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        await db.execute("INSERT INTO persons (name) VALUES ('지우')")
        cur = await db.execute("SELECT id FROM persons WHERE name = '지우'")
        person_id = (await cur.fetchone())[0]
        cur = await db.execute(
            "INSERT INTO faces (photo_path, bbox, det_score, embedding) VALUES (?, ?, ?, ?)",
            ("2024/unconfirmed.jpg", "[0,0,10,10]", 0.9, b"\x00" * 8),
        )
        face_id = cur.lastrowid
        await db.execute(
            "INSERT INTO face_matches (face_id, person_id, score) VALUES (?, ?, ?)",
            (face_id, person_id, 0.8),
        )
        await db.commit()

    r = await admin_client.get("/api/admin/tags/xmp-export")
    zf = _read_zip(r.content)
    assert zf.namelist() == []


async def test_export_xmp_includes_confirmed_face_region(admin_client):
    from backend.models.ai_database import _ai_db_path

    await _seed_meta("2024/group.jpg", width=1000, height=1000)
    async with aiosqlite.connect(_ai_db_path()) as db:
        await db.execute("INSERT INTO persons (name) VALUES ('지우')")
        cur = await db.execute("SELECT id FROM persons WHERE name = '지우'")
        person_id = (await cur.fetchone())[0]
        cur = await db.execute(
            "INSERT INTO faces (photo_path, bbox, det_score, embedding) VALUES (?, ?, ?, ?)",
            ("2024/group.jpg", "[100.0, 100.0, 300.0, 300.0]", 0.9, b"\x00" * 8),
        )
        face_id = cur.lastrowid
        await db.execute(
            "INSERT INTO face_labels (face_id, person_id) VALUES (?, ?)", (face_id, person_id)
        )
        await db.commit()

    r = await admin_client.get("/api/admin/tags/xmp-export")
    zf = _read_zip(r.content)
    assert zf.namelist() == ["2024/group.xmp"]
    content = zf.read("2024/group.xmp").decode("utf-8")
    assert "<mwg-rs:Name>지우</mwg-rs:Name>" in content
    assert 'stDim:w="1000" stDim:h="1000"' in content


async def test_export_xmp_multiple_photos_only_includes_qualifying_ones(admin_client):
    """대상 후보가 여러 장일 때 내보낼 게 있는 사진만 ZIP에 남아야 한다 — 기존
    테스트는 전부 후보 1장짜리라 zip_generator_from_content()의 반복 로직이 실제로
    루프 안에서 걸러내는지(우연히 통과하는 게 아니라) 검증하지 못했다."""
    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        # 내보낼 게 있는 사진
        await db.execute(
            "INSERT INTO photo_tags (photo_path, tag, source) VALUES "
            "('2024/tagged.jpg', '캠핑', 'ai')"
        )
        # 후보이지만(faces 행 존재) 확정 라벨이 없어 내보낼 게 없는 사진
        await db.execute("INSERT INTO persons (name) VALUES ('지우')")
        cur = await db.execute("SELECT id FROM persons WHERE name = '지우'")
        person_id = (await cur.fetchone())[0]
        cur = await db.execute(
            "INSERT INTO faces (photo_path, bbox, det_score, embedding) VALUES (?, ?, ?, ?)",
            ("2024/unconfirmed.jpg", "[0,0,10,10]", 0.9, b"\x00" * 8),
        )
        face_id = cur.lastrowid
        await db.execute(
            "INSERT INTO face_matches (face_id, person_id, score) VALUES (?, ?, ?)",
            (face_id, person_id, 0.8),
        )
        await db.commit()

    r = await admin_client.get("/api/admin/tags/xmp-export")
    zf = _read_zip(r.content)
    assert zf.namelist() == ["2024/tagged.xmp"]
    assert "캠핑" in zf.read("2024/tagged.xmp").decode("utf-8")


async def test_export_xmp_falls_back_to_full_filename_on_stem_collision(admin_client):
    """확장자만 다르고 stem이 같은 사진 쌍(RAW+JPEG 등)은 os.path.splitext(p)[0]
    기준 arcname이 서로 충돌한다 — 뒤에 처리되는 쪽이 앞의 .xmp를 덮어써 태그가
    조용히 사라지는 걸 막기 위해, 충돌 시 원본 파일명 전체 + .xmp로 대체해야 한다."""
    from backend.models.ai_database import _ai_db_path

    async with aiosqlite.connect(_ai_db_path()) as db:
        await db.execute(
            "INSERT INTO photo_tags (photo_path, tag, source) VALUES "
            "('2024/DSC_1234.NEF', '캠핑', 'ai'), ('2024/DSC_1234.jpg', '바다', 'ai')"
        )
        await db.commit()

    r = await admin_client.get("/api/admin/tags/xmp-export")
    zf = _read_zip(r.content)
    # ORDER BY photo_path(바이트 비교)로 '.NEF'가 '.jpg'보다 먼저 처리된다('N' < 'j').
    # 먼저 처리된 쪽이 짧은 이름을 선점하고, 나중에 처리된 쪽만 원본 파일명 전체로 대체된다.
    assert sorted(zf.namelist()) == ["2024/DSC_1234.jpg.xmp", "2024/DSC_1234.xmp"]
    assert "캠핑" in zf.read("2024/DSC_1234.xmp").decode("utf-8")
    assert "바다" in zf.read("2024/DSC_1234.jpg.xmp").decode("utf-8")


async def test_export_xmp_accepts_cookie_only_auth(admin_client):
    """Admin UI는 <a href download> 링크로 이 엔드포인트를 트리거하므로(JS fetch가
    아니라 브라우저 직접 네비게이션), Bearer 헤더 없이 admin_img_session 쿠키만으로도
    인증돼야 한다 — /thumb, /photo, /faces/{id}/crop과 동일한 패턴."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    cookie_only = AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", cookies=admin_client.cookies
    )
    try:
        r = await cookie_only.get("/api/admin/tags/xmp-export")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
    finally:
        await cookie_only.aclose()
