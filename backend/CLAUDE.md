# backend/CLAUDE.md

백엔드 상세 컨텍스트. 루트 → [`/CLAUDE.md`](../CLAUDE.md)

---

## 로컬 개발 명령

환경변수는 루트 `.env.example`을 복사해 `.env`로 사용하거나, 아래처럼 직접 설정한다.

```bash
# 의존성 설치 (런타임)
pip install -r backend/requirements.txt

# 개발 의존성 설치 (테스트용)
pip install pytest pytest-asyncio httpx numpy

# 환경변수 설정 — bash
export ADMIN_PASSWORD=dev_password
export JWT_SECRET=dev_secret_key
export PHOTO_ROOT=./testdata/photos
export DATA_DIR=./testdata/data
export BASE_URL=http://localhost:8080

# 환경변수 설정 — PowerShell
$env:ADMIN_PASSWORD="dev_password"; $env:JWT_SECRET="dev_secret_key"
$env:PHOTO_ROOT="./testdata/photos"; $env:DATA_DIR="./testdata/data"

# 개발 서버 실행 (hot-reload)
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8080
```

## 테스트

```bash
# 전체 실행 (pytest.ini: asyncio_mode=auto, testpaths=tests)
pytest

# 특정 파일만
pytest tests/test_auth.py

# 상세 출력
pytest -v
```

---

## 파일 구조

```
main.py              # FastAPI app, 미들웨어, 라우터 등록
routers/
  auth.py            # POST /api/auth/login|logout, GET /api/auth/me
  admin_browse.py    # GET /api/admin/browse|search|music. Phase 8: search()가 파일명 매칭 외 photo_tags 태그 매칭도 OR로 포함(services/photo_tags.py의 search_tag_matched_paths). GET /photo-info — Admin 라이트박스(정보보기 버튼) 단일 사진 EXIF·태그 조회, ADMIN_INFO_PANEL_SOURCES 전체(person/location 포함) 노출
  admin_albums.py    # CRUD /api/admin/albums/*
  admin_links.py     # CRUD /api/admin/albums/{id}/links
  admin_people.py    # Phase 2: 인물 CRUD, 얼굴 라벨/교정, 인물 사진 상세(슬라이드쇼용), 크롭 서빙, AI 잡 트리거, 경로 복구 승인
  admin_ai_tags.py   # Phase 5: 태그 목록/사진 그리드/삭제/일괄이름변경/수동태그추가 (photo_tags 기반, person·location은 조회만 또는 미노출). Phase 7: GET /tags/xmp-export — DB 메타데이터를 XMP 사이드카 ZIP으로 스트리밍 다운로드
  share.py           # GET|POST /api/share/{token}/*
  media.py           # /thumb/, /media/, /music/{token}?index=N 서빙
models/
  database.py        # SQLite 연결, 테이블 생성
  ai_database.py     # ai.db 연결 (Phase 2) — 스키마는 ai_worker/db.py와 동기 유지 필수
  schemas.py         # Pydantic 요청/응답 모델 + parse_music_paths()
services/
  thumbnail.py       # Pillow 썸네일 생성, EXIF 전체 메타 추출
  photo_meta.py      # photo_meta_cache 조회/적재 (load_photo_meta) — admin_browse/admin_albums/admin_people/share 공용
  photo_tags.py      # Phase 6: photo_tags 일괄 조회 (load_photo_tags) — 정보 패널(i 버튼) 태그 노출용, 뷰어별 source 노출 범위(ADMIN_INFO_PANEL_SOURCES/SHARE_INFO_PANEL_SOURCES) 정의. Phase 8: search_tag_matched_paths — 검색어를 태그에 포함하는 photo_path 조회(사진 탐색 검색용, source 구분 없음)
  xmp_export.py      # Phase 7: XMP 사이드카 생성 (build_xmp_content, load_locations, load_confirmed_regions) — dc:subject/mwg-rs:RegionList/Iptc4xmpExt:LocationCreated 매핑
  paths.py           # PHOTO_ROOT 하위 경로 resolve·containment 검증 (resolve_abs, assert_within_photo_root) — media/share 공용
  settings.py        # settings 테이블 조회 (get_settings, DEFAULTS) — admin_settings/admin_browse/admin_albums/share 공용
  auth.py            # JWT 생성/검증, bcrypt 해시 (ADMIN_PASSWORD_HASH 지원), admin_image_auth (이미지 서빙 인증)
  zip_stream.py      # 스트리밍 ZIP 생성 (zip_generator: 디스크 파일, zip_generator_from_content: 메모리 텍스트 — XMP export 전용)
  tag_vocab.py       # Phase 5: 수동 태그 추가용 어휘 목록 — ai_worker/tag_vocab.py의 label만 복제(컨테이너 분리로 코드 공유 불가, 어휘 바뀌면 양쪽 동기화 필요)
```

---

## 데이터 영속성

- `$DATA_DIR/db/app.db` — SQLite (albums, album_photos, share_links, thumbnail_cache)
- `$DATA_DIR/thumbnails/` — `MD5(file_path)_{size}.jpg` 형식 캐시 (재시작 후에도 유지)
- `$DATA_DIR/music/` — 배경음악 파일
- `$PHOTO_ROOT` — NAS 원본 사진 (읽기 전용, 절대 수정하지 않음)

---

## 핵심 설계 결정

### 시작 시 환경변수 경고
`JWT_SECRET` 또는 `ADMIN_PASSWORD`가 기본 dev 값이면 시작 로그에 `INSECURE CONFIGURATION` 경고가 출력된다. 프로덕션 배포 전 반드시 교체할 것.

### 인증 이중 구조
- **Admin**: JWT Bearer 토큰 (exp 8h) → `/api/admin/*` 전체 보호
- **공유 링크 사용자**: UUID 토큰으로 앨범 접근 → 패스워드 입력 후 httpOnly 세션 쿠키 발급 (exp 24h) → `/media/`, `/thumb/`, `/music/` 접근 허용

### 관리자 패스워드 인증
두 가지 방식 지원 — `ADMIN_PASSWORD_HASH`(bcrypt) 설정 시 우선 사용, 없으면 `ADMIN_PASSWORD` 평문 비교. 운영 환경에서는 bcrypt 해시 권장 (docker inspect 노출 위험 방지).

### 공유 링크 토큰
`secrets.token_hex(5)` (40비트, 10자). 속도 제한(5회 실패 → 15분 잠금)과 함께 충분한 보안 수준. 만료일(`expires_at`)과 활성화 플래그(`is_active`)를 모두 확인해야 유효.

### 배경음악 저장 구조
`albums.music_path` TEXT 컬럼에 JSON 배열 문자열 저장 (`["path1", "path2"]`). `parse_music_paths()` (schemas.py)로 읽기 시 파싱. 기존 단일 경로 문자열은 자동으로 1-element 리스트로 처리 (하위 호환). 음악 파일은 `DATA_DIR/music/` 하위에만 허용.

### 썸네일 및 EXIF
두 가지 크기 — small(300×200, 그리드/탐색기), medium(800×600, 슬라이드쇼 프리로드). 최초 요청 시 on-demand 생성. EXIF 전체 메타 추출: 촬영일·해상도·제조사·카메라·소프트웨어·셔터·조리개·ISO·초점거리·촬영모드·플래시·측광·노출모드. 탐색기/검색 EXIF는 `photo_meta_cache` 테이블에 캐싱(기준키: PHOTO_ROOT 상대 경로).

#### ⚠️ `_PHOTO_META_CACHE_VERSION` 운용 규칙 (`backend/models/database.py`)

아래 경우에 **반드시** `_PHOTO_META_CACHE_VERSION` 값을 +1 올린다:
- `photo_meta_cache` 테이블에 컬럼 추가/변경
- `thumbnail.py`의 `get_image_meta()` 추출 로직 변경으로 기존 캐시 값이 틀릴 수 있는 경우

버전을 올리면 컨테이너 재시작 시 기존 캐시 전체가 삭제되고, 다음 접근 때 EXIF를 새로 읽어 재구축한다.

**버전만 올리고 `_CACHE_INSERT_SQL` 변경은 불필요**: `_meta_to_row()`가 `_PHOTO_META_CACHE_VERSION`을 동적으로 참조하므로 자동 반영된다.

설계 불변식:
- `_CACHE_INSERT_SQL`에서 `cache_version`은 `?` 플레이스홀더로, `_meta_to_row()`가 마지막 원소로 `_PHOTO_META_CACHE_VERSION`을 넘긴다.
- SELECT 쿼리는 `cache_version >= ?`를 사용하며 `_PHOTO_META_CACHE_VERSION`을 파라미터로 전달한다 — 단일 경로: `services/photo_meta.py`의 `load_photo_meta()` (`admin_browse.py`의 `_enrich_photos`·`admin_albums.py`·`admin_people.py`·`share.py`가 이를 호출).
- EXIF 읽기 실패(`width is None`)는 캐시에 저장하지 않아 NAS 재접근 시 자동 재시도된다.

#### mtime 기반 캐시 무효화 (v4~)

`photo_meta_cache.mtime`에 캐시 적재 시점의 파일 mtime을 저장해둔다. `load_photo_meta()`는
캐시 히트여도 파일의 **현재** mtime을 조회해 캐시된 mtime과 비교하고, 다르면(외부 앱으로
EXIF를 직접 수정한 경우 등 파일 내용이 캐시 이후 바뀐 경우) 캐시 미스로 취급해 다시 읽는다
— `cache_version`만으로는 파일 내용이 바뀐 걸 감지할 수 없어서(버전은 스키마/추출 로직
변경에만 반응하는 전역 값) 별도로 필요한 검증이다. mtime 조회도 `EXIF_READ_CONCURRENCY`
세마포어로 동시 실행을 제한한다(캐시 히트마다 NAS에 stat 호출이 하나씩 더 나가는 트레이드오프,
단 전체 EXIF 재읽기보다는 훨씬 저렴). 파일이 아예 없어졌으면(mtime 조회 실패) 무효화하지
않고 캐시를 그대로 반환한다 — 원본 삭제 후에도 캐시로 정렬 등을 계속할 수 있어야 하기 때문
(`test_photo_sort_taken_at_uses_meta_cache`).

### ZIP 다운로드
`StreamingResponse` + `zipstream-ng` 청크 스트리밍으로 서버 메모리에 전체 파일을 올리지 않음. 응답 헤더에 `Content-Disposition: attachment` 설정.

### XMP export (Phase 7)
`GET /api/admin/tags/xmp-export` — 태그/위치/확정 인물을 사진별 `.xmp` 사이드카로 묶어 원본과 동일한 폴더 구조의 ZIP으로 스트리밍(`zip_stream.zip_generator_from_content`, 디스크 파일이 아니라 메모리에서 생성한 XML 텍스트를 담는 변형). 원본 사진은 절대 쓰지 않음.

- **대상 사진**: `photo_tags`/`photo_locations`/확정 `face_labels`(person_id NOT NULL) 중 하나라도 있는 사진만 — `UNION` 쿼리로 후보 목록을 구한 뒤, 사진별로 실제 내보낼 내용이 없으면(`has_exportable_content()`가 `False`) ZIP에서 제외.
- **얼굴 영역(`mwg-rs:RegionList`)은 `face_labels`로 확정된 것만** — `face_matches`(AI 추정, 미확정)는 얼굴 인식 승인 큐 취지상 제외. bbox(픽셀)를 0~1 비율로 정규화하려면 사진 width/height가 필요한데(`photo_meta_cache`, 기존 EXIF 캐시 재사용), 못 구하면 얼굴 영역이 있어도 `mwg-rs:Regions` 블록 자체를 생략(잘못된 비율보다 생략이 안전). **width/height 조회는 확정 얼굴이 있는 사진만 대상** — 라이브러리 전체(수만 장) 기준으로 `load_photo_meta()`를 부르면 캐시 미스마다 NAS EXIF 재읽기가 발생해 요청 하나가 수십 분~시간 단위로 걸릴 수 있어, 실제로 width/height가 필요한 대상(확정 얼굴이 있는 사진)으로만 좁힌다.
- **XMP 본문 생성은 ZIP 인코딩 시점까지 지연**(`xmp_export.xmp_bytes_iter`) — 대상이 라이브러리 전체일 수 있어, 모든 사진의 XMP 텍스트를 미리 만들어 리스트에 쌓아두면(문자열 수만 개, 컨테이너 `mem_limit` 대비 무시 못할 크기) 첫 바이트 응답 전에 메모리를 크게 잡아먹는다. `zip_generator_from_content()`에 완성된 문자열 대신 제너레이터를 넘기면 zipstream-ng가 각 항목을 실제로 인코딩할 때(스트리밍 중, 한 항목씩)까지 본문 생성을 미룬다 — "내보낼 게 있는지" 판단(`has_exportable_content()`)은 사전에 저렴하게 하고, 실제 XML 조립(`build_xmp_content()`)만 지연. 부수 효과로 이 조립도 `run_in_executor` 스레드 안에서 실행되어 이벤트 루프를 막지 않는다.
- **arcname은 `photo_path`에서 확장자만 뺀 stem** — RAW+JPEG처럼 같은 폴더에 stem이 같은 파일 쌍이 있으면 충돌하므로(먼저 처리된 쪽이 짧은 이름을 선점), 이미 쓰인 stem이면 원본 파일명 전체 + `.xmp`로 대체해 유일성을 보장한다(`admin_ai_tags.py`의 `seen_arcnames`). 후보 조회 쿼리에 `ORDER BY photo_path`를 둬 어떤 쪽이 짧은 이름을 갖는지 실행마다 달라지지 않게 한다.
- **`dc:subject`는 source 구분 없이 전체** — 정보 패널(`services/photo_tags.py`)과 달리 XMP export는 Admin 본인이 받는 개인 백업/이전용이라 뷰어별 프라이버시 분리가 필요 없음.
- **인증은 `admin_image_auth`(Bearer 또는 `admin_img_session` 쿠키)** — `get_current_admin`(Bearer 전용)이 아닌 이유: Admin UI가 JS blob 다운로드 없이 단순 `<a href download>` 링크로 트리거하기 때문(`/thumb`, `/photo`, `/faces/{id}/crop`과 동일 패턴).
- **XMP 패킷의 `xpacket begin` 속성값은 리터럴 BOM(U+FEFF) 한 글자**(XMP 스펙 요구사항) — 소스에 보이지 않는 문자를 직접 넣으면 편집 사고 위험이 커서 `chr(0xFEFF)`로 명시적으로 생성(`services/xmp_export.py`).

### 사진 탐색 검색에 태그 매칭 추가 (Phase 8)
`GET /api/admin/search`의 `q`가 기존 파일명 부분일치에 더해 `photo_tags` 태그 부분일치도 OR로 포함(`services/photo_tags.py`의 `search_tag_matched_paths`). doc/tagging_requirement.md의 `photo_tags` 미완료 항목 참고.

- **경로(path) 매칭은 재도입하지 않음** — 과거 파일명 검색에 상대 경로 매칭을 추가했다가(PR #82) 태그 검색과 개념이 겹칠 수 있어 되돌린 적 있음(PR #83, doc/todo/todo.md). 이번 범위는 태그 매칭만이고, 경로 매칭 재검토는 범위 밖.
- **source 구분 없이 전체 태그 대상** — 이 화면은 정보 패널처럼 노출 범위를 나눌 필요가 없는 Admin 전용 탐색기라, `person`(확정 인물명)·`location`까지 전부 검색 대상으로 포함해야 유용함.
- **LIKE 와일드카드(`%`, `_`) 이스케이프 필수** — 검색어를 그대로 `LIKE '%' || q || '%'`에 넣으면 `_`(임의의 한 글자) 한 글자만 검색해도 태그가 있는 사진이 전부 걸린다(`search_tag_matched_paths()`가 `\`로 이스케이프).
- **ai.db 조회 실패는 파일명 검색까지 막지 않음** — `search()`가 `search_tag_matched_paths()` 호출을 try/except로 감싸 실패 시 빈 집합으로 폴백(공유 링크 정보 패널의 ai.db 격리 원칙과 동일, Phase 6).
