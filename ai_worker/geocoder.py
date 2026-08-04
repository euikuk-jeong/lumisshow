"""GPS 좌표 → (도시, 국가) 역지오코딩. 오프라인 KD-tree 최근접 검색(reverse_geocoder,
GeoNames 기반)만 사용 — Kiwi를 LLM 대신 고른 것과 동일하게 외부 API/인터넷 의존성을
피하기 위함(doc/tagging_requirement.md).

reverse_geocoder는 영문(로마자) 도시명 + ISO 3166-1 alpha-2 국가코드만 반환한다.
국가명은 `_COUNTRY_NAMES_KO` 정적 매핑으로 한국어로 바꾼다(2026-08-02 결정).
도시명도 동일한 방식(`_CITY_NAMES_KO`, `(국가 한글명, 로마자 도시명)` 키)으로 실사용
중 관측된 지명을 커버(2026-08-05 결정) — 매핑에 없는 지명은 로마자 그대로 폴백한다
(전세계 지명을 저비용으로 완전히 옮길 방법은 없어 tag_vocab.py 어휘 큐레이션과 동일하게
"나오는 대로 추가"하는 방식). 매핑을 새로 추가한 뒤 이미 분석된 사진에도 소급 반영하려면
`retranslate_cities()`(재지오코딩 없이 DB 값만 갱신, `main.run_location_tag_reset()`)를
실행한다.
"""

import sqlite3

_geocoder = None


def _get_geocoder():
    """RGeocoder는 인스턴스 생성 시마다 ~30MB CSV를 다시 읽고 KD-tree를 재구축한다
    (reverse_geocoder.search()는 매 호출 이렇게 새 인스턴스를 만든다) — 사진 수만 장을
    순회하며 매번 호출하면 치명적으로 느려지므로 모듈 전역에 1회만 만들어 재사용한다.
    mode=1(단일 스레드 KD-tree)은 mode=2(멀티프로세스)가 요구하는
    `if __name__ == "__main__":` 가드도 필요 없어 워커 루프 안에서 안전하다."""
    global _geocoder
    if _geocoder is None:
        import reverse_geocoder as rg  # lazy import: 무거운 CSV 로딩 + KD-tree 구축

        _geocoder = rg.RGeocoder(mode=1, verbose=False)
    return _geocoder


def reverse_geocode(lat: float, lon: float) -> tuple[str | None, str | None]:
    """(city, country) 조회. country는 ISO 국가코드를 한국어 국가명으로 변환(매핑에
    없으면 코드 그대로 폴백), city는 (country, 원본 로마자명) 조합을 `_CITY_NAMES_KO`에서
    찾아 한국어로 변환(매핑에 없으면 로마자 그대로 폴백)."""
    result = _get_geocoder().query([(lat, lon)])[0]
    city = result.get("name") or None
    cc = result.get("cc") or None
    country = _COUNTRY_NAMES_KO.get(cc, cc) if cc else None
    if city and country:
        city = _CITY_NAMES_KO.get((country, city), city)
    return city, country


def sync_location_tag(conn: sqlite3.Connection, photo_path: str) -> None:
    """photo_tags(source='location')를 photo_locations의 현재 city/country에 맞춘다.
    photo_locations 행이 없으면(GPS 없음/삭제됨) 이전 위치 태그도 함께 제거한다 —
    photo_locations가 정본이므로 태그는 항상 그 상태를 뒤따라야 한다."""
    conn.execute(
        "DELETE FROM photo_tags WHERE photo_path = ? AND source = 'location'", (photo_path,)
    )
    row = conn.execute(
        "SELECT city, country FROM photo_locations WHERE photo_path = ?", (photo_path,)
    ).fetchone()
    if row is None:
        return
    # city/country를 각각 별도 태그 행으로 저장 — 하나로 합치면 "서울" 단독 검색이 안 됨.
    for value in (row["city"], row["country"]):
        if value:
            conn.execute(
                """INSERT INTO photo_tags (photo_path, tag, source) VALUES (?, ?, 'location')
                   ON CONFLICT(photo_path, tag, source) DO NOTHING""",
                (photo_path, value),
            )


def retranslate_cities(conn: sqlite3.Connection) -> int:
    """`_CITY_NAMES_KO`를 기존 `photo_locations.city`에 재적용한다 — 재지오코딩(파일
    열기·GPS 재계산) 없이 이미 저장된 값만 현재 매핑으로 갱신하므로 가볍다(DB 조회뿐).
    매핑에 새 지명을 추가한 뒤 이미 분석된 사진에도 소급 반영하고 싶을 때 쓴다
    (`main.run_location_tag_reset()`). 바뀐 행 수를 반환."""
    rows = conn.execute("SELECT photo_path, city, country FROM photo_locations").fetchall()
    changed = 0
    for row in rows:
        if not row["city"] or not row["country"]:
            continue
        new_city = _CITY_NAMES_KO.get((row["country"], row["city"]), row["city"])
        if new_city != row["city"]:
            conn.execute(
                "UPDATE photo_locations SET city = ? WHERE photo_path = ?",
                (new_city, row["photo_path"]),
            )
            sync_location_tag(conn, row["photo_path"])
            changed += 1
    return changed


# ISO 3166-1 alpha-2 → 한국어 국가명. 매핑에 없는 코드는 reverse_geocode()가 코드
# 그대로 폴백한다.
_COUNTRY_NAMES_KO: dict[str, str] = {
    "AD": "안도라", "AE": "아랍에미리트", "AF": "아프가니스탄", "AG": "앤티가바부다",
    "AI": "앵귈라", "AL": "알바니아", "AM": "아르메니아", "AO": "앙골라", "AQ": "남극",
    "AR": "아르헨티나", "AS": "아메리칸사모아", "AT": "오스트리아", "AU": "호주",
    "AW": "아루바", "AX": "올란드제도", "AZ": "아제르바이잔",
    "BA": "보스니아헤르체고비나", "BB": "바베이도스", "BD": "방글라데시", "BE": "벨기에",
    "BF": "부르키나파소", "BG": "불가리아", "BH": "바레인", "BI": "부룬디", "BJ": "베냉",
    "BL": "생바르텔레미", "BM": "버뮤다", "BN": "브루나이", "BO": "볼리비아",
    "BQ": "보네르섬", "BR": "브라질", "BS": "바하마", "BT": "부탄", "BV": "부베섬",
    "BW": "보츠와나", "BY": "벨라루스", "BZ": "벨리즈",
    "CA": "캐나다", "CC": "코코스제도", "CD": "콩고민주공화국", "CF": "중앙아프리카공화국",
    "CG": "콩고", "CH": "스위스", "CI": "코트디부아르", "CK": "쿡제도", "CL": "칠레",
    "CM": "카메룬", "CN": "중국", "CO": "콜롬비아", "CR": "코스타리카", "CU": "쿠바",
    "CV": "카보베르데", "CW": "퀴라소", "CX": "크리스마스섬", "CY": "키프로스", "CZ": "체코",
    "DE": "독일", "DJ": "지부티", "DK": "덴마크", "DM": "도미니카", "DO": "도미니카공화국",
    "DZ": "알제리",
    "EC": "에콰도르", "EE": "에스토니아", "EG": "이집트", "EH": "서사하라", "ER": "에리트레아",
    "ES": "스페인", "ET": "에티오피아",
    "FI": "핀란드", "FJ": "피지", "FK": "포클랜드제도", "FM": "미크로네시아",
    "FO": "페로제도", "FR": "프랑스",
    "GA": "가봉", "GB": "영국", "GD": "그레나다", "GE": "조지아", "GF": "프랑스령기아나",
    "GG": "건지", "GH": "가나", "GI": "지브롤터", "GL": "그린란드", "GM": "감비아",
    "GN": "기니", "GP": "과들루프", "GQ": "적도기니", "GR": "그리스",
    "GS": "사우스조지아사우스샌드위치제도", "GT": "과테말라", "GU": "괌",
    "GW": "기니비사우", "GY": "가이아나",
    "HK": "홍콩", "HM": "허드맥도널드제도", "HN": "온두라스", "HR": "크로아티아",
    "HT": "아이티", "HU": "헝가리",
    "ID": "인도네시아", "IE": "아일랜드", "IL": "이스라엘", "IM": "맨섬", "IN": "인도",
    "IO": "영국령인도양지역", "IQ": "이라크", "IR": "이란", "IS": "아이슬란드", "IT": "이탈리아",
    "JE": "저지", "JM": "자메이카", "JO": "요르단", "JP": "일본",
    "KE": "케냐", "KG": "키르기스스탄", "KH": "캄보디아", "KI": "키리바시", "KM": "코모로",
    "KN": "세인트키츠네비스", "KP": "북한", "KR": "대한민국", "KW": "쿠웨이트",
    "KY": "케이맨제도", "KZ": "카자흐스탄",
    "LA": "라오스", "LB": "레바논", "LC": "세인트루시아", "LI": "리히텐슈타인",
    "LK": "스리랑카", "LR": "라이베리아", "LS": "레소토", "LT": "리투아니아",
    "LU": "룩셈부르크", "LV": "라트비아", "LY": "리비아",
    "MA": "모로코", "MC": "모나코", "MD": "몰도바", "ME": "몬테네그로", "MF": "생마르탱",
    "MG": "마다가스카르", "MH": "마셜제도", "MK": "북마케도니아", "ML": "말리",
    "MM": "미얀마", "MN": "몽골", "MO": "마카오", "MP": "북마리아나제도",
    "MQ": "마르티니크", "MR": "모리타니", "MS": "몬트세랫", "MT": "몰타", "MU": "모리셔스",
    "MV": "몰디브", "MW": "말라위", "MX": "멕시코", "MY": "말레이시아", "MZ": "모잠비크",
    "NA": "나미비아", "NC": "뉴칼레도니아", "NE": "니제르", "NF": "노퍽섬", "NG": "나이지리아",
    "NI": "니카라과", "NL": "네덜란드", "NO": "노르웨이", "NP": "네팔", "NR": "나우루",
    "NU": "니우에", "NZ": "뉴질랜드",
    "OM": "오만",
    "PA": "파나마", "PE": "페루", "PF": "프랑스령폴리네시아", "PG": "파푸아뉴기니",
    "PH": "필리핀", "PK": "파키스탄", "PL": "폴란드", "PM": "생피에르미클롱",
    "PN": "핏케언제도", "PR": "푸에르토리코", "PS": "팔레스타인", "PT": "포르투갈",
    "PW": "팔라우", "PY": "파라과이",
    "QA": "카타르",
    "RE": "레위니옹", "RO": "루마니아", "RS": "세르비아", "RU": "러시아", "RW": "르완다",
    "SA": "사우디아라비아", "SB": "솔로몬제도", "SC": "세이셸", "SD": "수단",
    "SE": "스웨덴", "SG": "싱가포르", "SH": "세인트헬레나", "SI": "슬로베니아",
    "SJ": "스발바르얀마옌제도", "SK": "슬로바키아", "SL": "시에라리온", "SM": "산마리노",
    "SN": "세네갈", "SO": "소말리아", "SR": "수리남", "SS": "남수단",
    "ST": "상투메프린시페", "SV": "엘살바도르", "SX": "신트마르턴", "SY": "시리아",
    "SZ": "에스와티니",
    "TC": "터크스케이커스제도", "TD": "차드", "TF": "프랑스령남방및남극지역", "TG": "토고",
    "TH": "태국", "TJ": "타지키스탄", "TK": "토켈라우", "TL": "동티모르",
    "TM": "투르크메니스탄", "TN": "튀니지", "TO": "통가", "TR": "튀르키예",
    "TT": "트리니다드토바고", "TV": "투발루", "TW": "대만", "TZ": "탄자니아",
    "UA": "우크라이나", "UG": "우간다", "UM": "미국령군소제도", "US": "미국",
    "UY": "우루과이", "UZ": "우즈베키스탄",
    "VA": "바티칸", "VC": "세인트빈센트그레나딘", "VE": "베네수엘라",
    "VG": "영국령버진아일랜드", "VI": "미국령버진아일랜드", "VN": "베트남", "VU": "바누아투",
    "WF": "왈리스푸투나", "WS": "사모아",
    "XK": "코소보",
    "YE": "예멘", "YT": "마요트",
    "ZA": "남아프리카공화국", "ZM": "잠비아", "ZW": "짐바브웨",
}


# (한국어 국가명, reverse_geocoder 원본 로마자 도시명) → 한국어 지명. 실사용 중
# `photo_locations`에 관측된 지명만 큐레이션(전세계 완전 커버는 목표하지 않음,
# tag_vocab.py와 동일한 "나오는 대로 추가" 방식). 매핑에 없으면 로마자 그대로 폴백.
# 새 지명을 추가한 뒤 기존 사진에 소급 반영하려면 retranslate_cities() 실행.
_CITY_NAMES_KO: dict[tuple[str, str], str] = {
    ("대한민국", "Seoul"): "서울",
    ("대한민국", "Incheon"): "인천",
    ("대한민국", "Daegu"): "대구",
    ("대한민국", "Kwangmyong"): "광명",
    ("대한민국", "Koesan"): "괴산",
    ("대한민국", "Santyoku"): "삼척",
    ("대한민국", "Anseong"): "안성",
    ("대한민국", "Bucheon-si"): "부천",
    ("대한민국", "Kurye"): "구례",
    ("대한민국", "Gaigeturi"): "애월",
    ("대한민국", "Gwanin"): "관인",
    ("대한민국", "Anyang-si"): "안양",
    ("대한민국", "Gapyeong"): "가평",
    ("대한민국", "Guri-si"): "구리",
    ("대한민국", "Seogwipo"): "서귀포",
    ("대한민국", "Chinch'on"): "진천",
    ("대한민국", "Jangheung"): "장흥",
    ("대한민국", "Seongnam-si"): "성남",
    ("대한민국", "Kwangju"): "광주",
    ("대한민국", "Suwon-si"): "수원",
    ("대한민국", "Jeongok"): "전곡",
    ("대한민국", "Songgang-dong"): "송강동",
    ("대한민국", "Tonghae"): "동해",
    ("대한민국", "Hongch'on"): "홍천",
    ("대한민국", "Nangen"): "남원",
    ("대한민국", "Goyang-si"): "고양",
    ("대한민국", "Yangp'yong"): "양평",
    ("대한민국", "Hwaseong-si"): "화성",
    ("대한민국", "Neietsu"): "영월",
    ("대한민국", "Tanhyeon"): "탄현",
    ("대한민국", "Seonwon"): "선원",
    ("대한민국", "T'aebaek"): "태백",
    ("대한민국", "Wabu"): "와부",
    ("대한민국", "Haseong"): "하성",
    ("대한민국", "Sindong"): "신동",
    ("대한민국", "Hwacheon"): "화천",
    ("대한민국", "Yeoncheon"): "연천",
    ("대한민국", "Cheongpyeong"): "청평",
    ("대한민국", "Kang-neung"): "강릉",
    ("대한민국", "Uijeongbu-si"): "의정부",
    ("대한민국", "Wonju"): "원주",
    ("대한민국", "Gwangjeok"): "광적",
    ("대한민국", "Beobwon"): "법원",
    ("대한민국", "Hanam"): "하남",
    ("대한민국", "Jeju-si"): "제주",
    ("대한민국", "Naju"): "나주",
    ("대한민국", "Osan"): "오산",
    ("대한민국", "Sangju"): "상주",
    ("베트남", "Nha Trang"): "나트랑",
    ("베트남", "Cam Lam"): "깜람",
    ("가나", "Takoradi"): "타코라디",
    ("일본", "Beppu"): "벳푸",
    ("일본", "Fukuoka-shi"): "후쿠오카",
    ("일본", "Chikushino-shi"): "치쿠시노",
    ("일본", "Hita"): "히타",
    ("일본", "Bungo-Takada-shi"): "분고타카다",
}
