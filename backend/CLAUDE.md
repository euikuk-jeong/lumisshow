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
  admin_browse.py    # GET /api/admin/browse|search|music
  admin_albums.py    # CRUD /api/admin/albums/*
  admin_links.py     # CRUD /api/admin/albums/{id}/links
  admin_people.py    # Phase 2: 인물 CRUD, 얼굴 라벨/교정, 인물 사진 상세(슬라이드쇼용), 크롭 서빙, AI 잡 트리거, 경로 복구 승인
  admin_ai_tags.py   # Phase 5: 태그 목록/사진 그리드/삭제/일괄이름변경/수동태그추가 (photo_tags 기반, person·location은 조회만 또는 미노출)
  share.py           # GET|POST /api/share/{token}/*
  media.py           # /thumb/, /media/, /music/{token}?index=N 서빙
models/
  database.py        # SQLite 연결, 테이블 생성
  ai_database.py     # ai.db 연결 (Phase 2) — 스키마는 ai_worker/db.py와 동기 유지 필수
  schemas.py         # Pydantic 요청/응답 모델 + parse_music_paths()
services/
  thumbnail.py       # Pillow 썸네일 생성, EXIF 전체 메타 추출
  photo_meta.py      # photo_meta_cache 조회/적재 (load_photo_meta) — admin_browse/admin_albums/admin_people/share 공용
  paths.py           # PHOTO_ROOT 하위 경로 resolve·containment 검증 (resolve_abs, assert_within_photo_root) — media/share 공용
  settings.py        # settings 테이블 조회 (get_settings, DEFAULTS) — admin_settings/admin_browse/admin_albums/share 공용
  auth.py            # JWT 생성/검증, bcrypt 해시 (ADMIN_PASSWORD_HASH 지원), admin_image_auth (이미지 서빙 인증)
  zip_stream.py      # 스트리밍 ZIP 생성
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
