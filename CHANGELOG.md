# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.8.2] - 2026-06-23

### Fixed
- **세션 메모리 누수 수정**: 공유 링크 조회수 중복 방지용 `_counted_sessions` dict가 만료된 항목을 정리하지 않아 장시간 실행 컨테이너에서 무한 증가하던 문제 수정 — 각 요청 전 TTL 만료 항목 자동 퇴거 추가 (`share.py`)

### Security
- **Admin 로그인 무차별 대입 방지**: 동일 IP에서 5회 연속 로그인 실패 시 15분 잠금 적용 — `share_link_failures` 테이블 `admin:{ip}` 키 재사용으로 컨테이너 재시작 후에도 잠금 상태 유지 (`auth.py`)

## [0.8.1] - 2026-06-22

### Fixed
- **슬라이드쇼 사진 품질 저하 수정**: 슬라이드쇼가 원본 대신 800×600 JPEG 썸네일(`thumb_medium_url`)을 표시하던 문제 수정 — `photo.url`(원본)로 교체. 초기 표시·전환·프리로드 모두 수정 (`slideshow.js`)
- **공유 뷰어 사진 단독 보기 품질 저하 수정**: 썸네일 클릭 시 나타나는 단독 보기 화면도 동일하게 썸네일이 표시되던 문제 수정 (`album-view.js`)
- **Admin 라이트박스 품질 저하 수정**: 앨범 편집·탐색기 라이트박스가 medium 썸네일을 표시하던 문제 수정 — `GET /api/admin/photo` 엔드포인트 신규 추가하여 원본 직접 서빙 (`lightbox.js`, `admin_browse.py`)

## [0.8.0] - 2026-06-22

### Performance
- **슬라이드쇼 진보적 로딩**: 첫 50장을 즉시 시작 후 나머지를 백그라운드에서 로드 — 대용량 앨범(500장+)에서 진입 지연 대폭 감소 (`slideshow.js`)
- **photo_meta_cache 전체 EXIF 저장**: `taken_at`·`width`·`height` 3개 → `make`·`camera`·`shutter`·`aperture`·`iso` 등 15개 컬럼으로 확장, `cache_version` 마킹으로 구 캐시 자동 무효화 (`database.py`, `admin_browse.py`, `share.py`)
- **N+1 DB 쿼리 제거**: `_enrich_photos()`에서 사진별 개별 쿼리 → `WHERE file_path IN (?, ...)` 단일 쿼리 (청크 900) (`admin_browse.py`)
- **검색 전량 enrich 제거**: 날짜 필터 없을 때 해당 페이지 사진만 EXIF enrich — 10,000장 중 20장 요청 시에도 전량 처리하던 구조 개선 (`admin_browse.py`)
- **썸네일 앨범 검증 쿼리 감소**: 토큰별 30초 TTL 인메모리 캐시로 그리드 100장 로드 시 DB 쿼리 100회 → 1회 (`media.py`)
- **서브폴더 child_count 산출 개선**: `os.scandir()` → `os.listdir()`로 불필요한 stat 오버헤드 제거 (`admin_browse.py`)
- **`_photo_root()` 중복 계산 제거**: 각 핸들러에서 요청당 1회 계산 후 하위 함수에 전달 (`admin_browse.py`, `media.py`)

### Added
- **사진 목록 페이지네이션**: `GET /api/share/{token}/photos?page=N&size=N` 파라미터 추가 — 기본(size=0)은 전체 반환으로 하위 호환 (`share.py`, `schemas.py`)

### Fixed
- **슬라이드쇼 info 패널 EXIF 미표시**: 기존 `photo_meta_cache` 행에 신규 EXIF 컬럼이 NULL로 남아 info 패널이 비던 문제 — `cache_version < 1` 행을 앱 기동 시 자동 삭제 후 재캐싱 (`database.py`)
- **썸네일 동시 생성 레이스 컨디션**: 존재 체크와 생성 사이 동시 요청 시 중복 생성 시도 가능하던 문제 — per-path `threading.Lock` 적용 (`thumbnail.py`)

### Security
- **브루트포스 잠금 DB 저장**: `_fail_registry` 메모리 dict → `share_link_failures` SQLite 테이블로 교체 — 컨테이너 재시작 후에도 잠금 상태 유지 (`share.py`, `database.py`)

## [0.7.0] - 2026-06-22

### Added
- **공유 뷰어 사진 확대 중 슬라이드쇼 바로 시작**: 사진 단독 확대 보기 하단에 "▶ 슬라이드쇼" 버튼 추가 — 현재 보고 있는 사진 인덱스 기준으로 슬라이드쇼 즉시 진입 (`album-view.js`)

### Fixed
- **설정 패널 취소 시 DOM 롤백**: 값 변경 후 취소(버튼·백드롭 클릭 모두)하면 다음 번 패널 열 때 저장된 값으로 복원됨 (`album-view.js`)
- **사진 추가 중복 피드백**: 탐색기에서 이미 앨범에 있는 사진 추가 시 "N장 추가됨, M장 중복 제외" alert 표시 — `POST /api/admin/albums/{id}/photos` 응답에 `added`/`skipped` 건수 추가 (`admin_albums.py`, `admin-browse.js`)

### Changed
- **앨범 목록 로딩 깜빡임 개선**: 재방문 시 이전 결과를 즉시 표시 후 백그라운드 갱신 (모듈 캐시 적용) (`admin-albums.js`)
- **Unit Test 커버리지 확대**: 158개 → 159개 — `POST /photos` 빈 경로 목록·중복 건수 반환 테스트 추가

## [0.6.1] - 2026-06-22

### Fixed
- **라이트박스 키보드 이벤트 리스너 누적 방지**: `close()` 함수에 `closed` 플래그 추가 — 비동기 삭제 중 Escape 등 중복 호출 경로에서 `removeEventListener`가 항상 정확히 1회 실행됨 (`lightbox.js`)
- **비루프 슬라이드쇼 경계값 오동작 수정**: `loop=false`일 때 첫 사진에서 역방향(←) 이동 시 마지막 사진으로 이동하던 모듈로 연산 오류 수정 — 경계에서 `advance()` 호출 차단 (`slideshow.js`)
- **공유 링크 메모리 무한 누적 방지**: `_fail_registry`에 `recorded_at` 타임스탬프 추가, `_counted_sessions`를 `set` → `dict[cookie, expires_at]`으로 변경 — `_purge_stale()` 기회적 정리로 장기 운영 시 메모리 누수 해소 (`share.py`)

### Changed
- **Unit Test 커버리지 확대**: 기존 53개 → 158개 (105개 추가)
  - `test_admin_settings.py` 신규 (11개): GET 기본값, PATCH 각 필드, 인증 검증
  - `test_admin_albums.py` 추가 (9개): 앨범 복제(`duplicate_album`) 5개, 조회수 리셋(`reset_view_count`) 3개, 인증 1개
  - `test_share.py` 추가 (2개): 조회수 첫 접속 증가, 동일 세션 중복 방지
  - `test_browse.py` 추가 (5개): `list_music` 빈 폴더·오디오 반환·비오디오 필터·rel 경로·인증

## [0.6.0] - 2026-06-22

### Added
- **슬라이드쇼 속도 즉시 조절**: 툴바에 −/Ns/+ 버튼 추가 — 재생 중 전환 간격을 2·3·5·8·10·15·20·30초 프리셋으로 즉시 변경, localStorage 저장
- **앨범 복제**: 앨범 편집 페이지 우상단 "복제" 버튼 — 앨범 설정(테마·슬라이드쇼·음악)과 사진 목록 전체를 새 앨범으로 복사 (`POST /api/admin/albums/{id}/duplicate`)

### Changed
- **슬라이드쇼 사진 비율 개선**: `object-fit: cover` → `contain`으로 변경, 남는 여백을 동일 사진의 블러 버전으로 채워 사진 전체 구도가 잘리지 않고 표시됨
- **앨범 편집 모바일 섹션 순서 변경**: `grid-template-areas` 적용 — 모바일(768px 이하)에서 기본 정보 → 슬라이드쇼 기본 설정 → 공유 링크 → 사진 순으로 재배치

## [0.5.2] - 2026-06-22

### Fixed
- Admin 설정 페이지 진입 시 서버의 `ui_theme` 값을 localStorage에 동기화 — 한 기기에서 테마를 변경한 뒤 다른 기기에서 설정 페이지를 열면 변경된 테마가 즉시 반영됨

## [0.5.1] - 2026-06-22

### Changed
- 슬라이드쇼 툴바 배경 완전 투명화: 모든 디바이스에서 하단 버튼 영역 그라디언트·블러 제거
- 모바일 중앙 탭 동작 변경: 툴바 표시 → 즉시 숨김 토글 (`toggleUI`)
- 모바일에서 `mousemove` 리스너 미등록: 터치 후 브라우저가 생성하는 합성 mousemove 이벤트로 툴바가 다시 표시되던 문제 수정

## [0.5.0] - 2026-06-21

### Added
- **사진 단독 확대 보기**: 공유 앨범 화면에서 썸네일 클릭 시 슬라이드쇼 대신 해당 사진만 전체화면으로 확대 표시
  - 하단에 파일명 · 현재 번호/전체 수 표시
  - 다운로드 버튼 및 EXIF 정보 보기 버튼 (슬라이드쇼와 동일 기능)
  - 좌우 화살표 버튼 및 키보드(←/→/Esc) 탐색
- **줌인/아웃**: 확대 보기 화면에서 다양한 방법으로 사진 확대/축소
  - 마우스 휠: 커서 위치 기준 확대/축소
  - 더블클릭: 클릭 위치 기준 2× 확대 / 원래 크기 복귀 토글
  - 드래그: 확대 상태에서 이미지 패닝
  - 핀치 제스처 (모바일): 두 손가락 핀치로 줌인/아웃 + 패닝
  - 키보드 `+`/`-`: 1.3× 단계 줌인/아웃, `0`: 리셋
  - 마우스 가운데 버튼: 줌 즉시 초기화

## [0.4.3] - 2026-06-21

### Changed
- 슬라이드쇼 전환 효과 목록(`EFFECTS`), 라벨, 기본 설정, `loadSlideshowSettings` 함수를 `slideshow-config.js` 공유 모듈로 추출 — 4개 파일에 분산되어 있던 중복 정의 제거
- 슬라이드쇼 시작 시 `?i=N` URL 파라미터 제거 (`history.replaceState`) — 특정 사진에서 시작 후 URL이 깔끔하게 정리됨

## [0.4.2] - 2026-06-21

### Fixed
- 사진이 없는 앨범의 공유 뷰어에서 전체 다운로드 버튼 비활성화 처리

## [0.4.1] - 2026-06-21

### Changed
- 신규 앨범 생성 시 기본 테마를 서버 기본(`null`)으로 설정 — 서버 테마 변경 시 기본값 앨범 전체에 자동 반영

## [0.4.0] - 2026-06-21

### Added
- **멀티 테마 시스템**: 8종 테마 지원 — Dark / OLED Black / Slate / Warm Dark / Light / Sepia / Sky / Rose
- **Glassmorphism UI**: 네비게이션 바·모달·뷰어 설정 패널·슬라이드쇼 툴바에 `backdrop-filter: blur()` frosted glass 적용
- **Liquid Glass 요소**: Primary 버튼 hover glow, ghost 버튼 반투명 배경, 선택 상태 glow outline
- **Elevation 시스템**: 그림자 대신 lightness 기반 4단계 표면 계층 + 카드 상단 inset highlight
- **앨범별 테마 설정**: 앨범 편집 화면에서 각 앨범에 독립 테마 지정 가능
- **서버 기본 테마 옵션**: 앨범 테마를 '서버 기본'으로 설정하면 Admin 설정의 기본 테마를 자동 적용
- **Admin 테마 서버 저장**: Admin 설정에서 테마 변경 시 서버에도 저장 → 신규 앨범 생성 시 해당 테마가 기본값으로 적용
- **테마 모듈** (`theme.js`): 테마 목록·색상 정의, localStorage 기반 개인 설정 관리
- **FOUC 방지**: `<head>` 인라인 스크립트로 페이지 렌더 전 `data-theme` 즉시 설정

### Changed
- Admin UI 테마가 뷰어에서 앨범 테마로 변경된 뒤 Admin 페이지로 돌아올 때 개인 테마(localStorage)로 자동 복원
- `AlbumResponse.ui_theme = null`은 서버 기본 테마 사용을 의미 (기존 앨범은 null → 서버 기본값 적용)

## [0.3.8] - 2026-06-21

### Added
- 탐색기 숨김 경로 설정 기능: Admin 설정에서 사진 탐색 화면에 표시하지 않을 폴더를 관리 (PHOTO_ROOT 기준 상대 경로)
- 숨김 경로 전용 관리 화면 (`/admin/hidden-paths`): 목록 조회·추가·삭제·저장, 설정 페이지에 개수 배지 표시
- 경로 추가 시 서버에서 실제 폴더 존재 여부를 사전 검증하여 오입력 방지 (`GET /api/admin/path-exists`)

## [0.3.7] - 2026-06-20

### Added
- 앨범 편집 화면 공유 링크에 삭제 버튼 추가: 활성 링크는 비활성화 후 삭제, 비활성/만료 링크는 바로 삭제

### Fixed
- 공유 링크 삭제 후 새 링크 생성 시 삭제된 링크가 목록에 다시 표시되던 버그 수정

## [0.3.6] - 2026-06-20

### Added
- NAS 원클릭 배포 스크립트 추가 (`scripts/nas-update.sh`): pull → 중지 → 재시작 → 구버전 이미지 정리를 SSH 커맨드 하나로 수행

### Fixed
- 공유 링크 토큰 길이 복원: `token_urlsafe(16)` (22자) → `token_hex(5)` (10자). 속도 제한(5회 실패 → 15분 잠금)으로 충분한 보안 수준 유지

## [0.3.5] - 2026-06-20

### Security
- Admin 썸네일 URL에서 JWT 노출 제거: `?token=` 쿼리 파라미터 방식을 httpOnly 쿠키(`admin_img_session`) 방식으로 교체하여 nginx 로그·브라우저 히스토리에 8h admin JWT가 노출되지 않도록 수정

## [0.3.4] - 2026-06-19

### Changed
- 모바일 슬라이드쇼 툴바 버튼 크기 확대: 터치 타겟 ~32px → ~40px (font-size 16→18px, 수직 패딩 8→11px)

## [0.3.3] - 2026-06-19

### Fixed
- 슬라이드쇼 정보 패널 EXIF 미표시 문제: `share.py`에서 상대 경로를 절대 경로로 변환하지 않아 PIL이 파일을 찾지 못하던 버그 수정
- ZIP 다운로드 시 상대 경로를 절대 경로로 변환하지 않아 파일이 포함되지 않던 버그 수정

## [0.3.2] - 2026-06-19

### Security
- 공유 링크 토큰 강도 강화: `secrets.token_hex(5)` (40비트) → `secrets.token_urlsafe(16)` (128비트)
- `album_photos.file_path` 절대 경로 → PHOTO_ROOT 기준 상대 경로 저장 (서버 파일시스템 구조 노출 방지)

### Fixed
- ZIP 다운로드가 전체 아카이브를 메모리에 올리던 문제 수정: `zipstream-ng` 청크 스트리밍으로 교체
- 탐색기(`/browse`, `/search`) 요청마다 PIL로 EXIF 재읽기 하던 성능 문제: `photo_meta_cache` 테이블 캐싱 추가
- DB 마이그레이션 예외 처리 범위 축소: `except Exception` → `except OperationalError` (실제 오류 은폐 방지)
- 테스트 13건 오류 수정 (PUT/PATCH 메서드 불일치, 토큰 길이, EXIF 필드수, Windows 경로 구분자)

## [0.3.1] - 2026-06-18

### Added
- 사진 탐색 화면 개선
  - Synology NAS 시스템 폴더 자동 숨김 (`@eaDir`, `#recycle`, `@tmp`, `#snapshot` 등)
  - 리스트 보기 / 그리드 보기 토글 (⊞/☰)
  - 정렬 옵션 추가: 파일명 오름차순/내림차순, 날짜 오름차순/내림차순
  - 전체 선택 / 전체 해제 버튼 항상 표시
  - 사진 클릭 시 라이트박스 확대 보기 (체크박스로 선택)
  - 라이트박스 하단에 선택 상태 표시 (선택/✓ 선택됨 + 현재 선택 수/전체 수)
- 앨범 편집 화면 개선
  - 사진 썸네일 클릭 시 라이트박스 확대 보기
  - 리스트 보기 / 그리드 보기 토글 (⊞/☰)
  - 라이트박스 하단에 "커버로 설정" / "앨범에서 삭제" 액션 버튼

### Fixed
- 앨범 편집 리스트 보기에서 "커버로 설정" 버튼이 보이지 않던 문제 수정

## [0.3.0] - 2026-06-18

### Added
- 모바일 슬라이드쇼 탭존 내비게이션: 스와이프 제스처 대신 화면 좌(35%)/우(35%) 탭으로 이전/다음 이동
  - 중앙(30%) 탭 시 툴바 표시/숨김 토글
  - 탭존 힌트 화살표(‹ ›) 툴바와 연동하여 자동 페이드
- 모바일 슬라이드쇼 진입 시 자동 전체화면 + orientation lock 시도

### Changed
- 모바일 Portrait 처리: CSS 90도 회전 방식 → 16:9 letterbox 방식으로 교체
  - 전체화면에서도 letterbox 유지 (`document.documentElement` 기준 fullscreen)
- 모바일 감지 기준: `max-width: 600px` → `(pointer: coarse) and (hover: none)` 미디어쿼리

### Fixed
- 핀치줌/더블탭 줌으로 슬라이드쇼 레이아웃 깨지는 문제: `user-scalable=no` + `touch-action: none`
- iOS 뒤로가기 스와이프와 슬라이드쇼 스와이프 충돌: 탭존 방식으로 전환해 충돌 원천 차단
- favicon.ico 404 로그 제거: `<link rel="icon" href="data:,">` 추가

## [0.2.6] - 2026-06-18

### Added
- 앨범 커버 미지정 시 정렬 기준 첫 번째 사진 자동 표시 (DB 저장 없음, `first_photo_path` API 응답 추가)
- 앨범 조회수 기능: 슬라이드쇼 접속 시 +1 누적, 앨범 목록 카드 및 편집 화면 기본 정보에 표시
  - 앨범 편집 기본 정보에 조회수 + 초기화 버튼 추가
  - 동일 세션(쿠키) 기준 새로고침 중복 카운트 방지

## [0.2.5] - 2026-06-18

### Added
- 앨범 사진 정렬 기능: 앨범 편집 화면 사진 섹션에 정렬 버튼 추가 ("+사진 추가" 왼쪽)
  - 정렬 기준: 파일명 / 촬영일(EXIF 기반), 기본값: 촬영일 오름차순
  - 방향: 오름차순 / 내림차순
  - 적용 시 album_photos.sort_order 실체화 → 슬라이드쇼·공유 뷰어 자동 반영
  - 사진 추가 시에도 앨범 sort 설정에 맞게 자동 재정렬
  - 촬영일 EXIF 없는 사진은 파일명으로 tiebreak

## [0.2.4] - 2026-06-17

### Added
- Admin 설정 메뉴 추가 (사진 탐색 · 로그아웃 사이에 배치)
  - 서버 타임존 설정: 검색 가능한 드롭다운, 49개 글로벌 타임존 지원
  - 슬라이드쇼 전역 기본값 설정 (전환 시간·순서·효과·음악·음량·반복)
- 앨범별 슬라이드쇼 기본 설정: 앨범 편집 화면에 "슬라이드쇼 기본 설정" 섹션 추가
  - 앨범마다 개별 슬라이드쇼 설정을 DB에 저장
  - 신규 앨범 생성 시 서버 전역 설정값으로 자동 초기화
- 공유 링크 뷰어에 앨범별 기본 설정 적용: 뷰어 진입 시 앨범 DB 설정값 사용
  - 뷰어에서 변경한 설정은 로컬(localStorage, 토큰별)에만 저장되고 DB는 변경되지 않음

### Fixed
- 공유 링크 만료일 처리 버그 수정
  - 타임존 오프셋이 포함된 만료일을 UTC로 정규화하여 SQLite에 저장
  - 음수 UTC 오프셋(예: EST UTC-5)에서 만료 비교가 잘못되던 문제 해결
  - Admin UI에서 만료된 링크를 "활성" 으로 잘못 표시하던 버그 수정 ("만료됨" 배지 추가)
- 만료일 표시를 서버 타임존 기준으로 변환하여 정확하게 표시

## [0.2.3] - 2026-06-17

### Changed
- 크레딧 표기 변경: `© euikuk.jeong` → `Made by Ekjeong`

## [0.2.2] - 2026-06-17

### Fixed
- 버전 표시 이중 `v` 접두사 제거 (`vv0.2.1` → `v0.2.1`)

### Changed
- Admin 네비바 및 뷰어 하단에 `© euikuk.jeong` copyright 추가

## [0.2.1] - 2026-06-17

### Added
- Admin 네비바 및 뷰어 하단에 버전 정보 표시 (`GET /version` 공개 엔드포인트)
- `localtest.sh` 추가 (Git Bash용, git tag 기준 버전 자동 감지)

### Fixed
- `localtest.bat` 콘솔 한글 깨짐 → 영문으로 변경
- `localtest.bat`에서 APP_VERSION git tag 자동 설정 (CMD에서 동작 안 하는 문제)

### Changed
- Dockerfile에 `ARG/ENV APP_VERSION` 추가, 릴리즈 시 git tag 자동 주입

## [0.2.0] - 2026-06-17

### Added
- 풀스크린 버튼 추가 (⛶ / ⊡ 토글, `requestFullscreen` API)
- 반복 재생 설정 옵션 (켜기: 순환 / 끄기: 마지막 사진에서 정지)
- 반복 완료 토스트: 사이클 종료 시 '🔁 처음부터 다시 재생' 3초 표시
- 종료 토스트: 마지막 사진 인터벌 후 '슬라이드쇼가 종료되었습니다' 10초 표시
- `localtest.bat`: LAN IP 자동 감지 포함 로컬 개발 서버 실행 스크립트

### Changed
- 모바일 반응형 레이아웃: 화살표·볼륨 슬라이더·info 버튼 숨김, 툴바 버튼 축소
- landscape 강제 고정: CSS `rotate(90deg)` (portrait 미디어쿼리) + `screen.orientation.lock` 병행
- 터치 스와이프 좌표 보정: portrait CSS 회전 시 축 매핑 처리
- UI 자동 숨김: 마우스/탭 없을 시 3초 후 툴바·화살표 페이드 아웃
- 음량 기본값 60% → 25%

## [0.1.0] - 2026-06-16

### Added
- 앨범 관리 (생성/편집/삭제, 사진 추가·제외, 앨범 커버 설정)
- 공유 링크 생성 (비밀번호·만료일 설정, UUID 토큰 방식)
- 슬라이드쇼 전환 효과 9종 + Ken Burns 효과 (8방향 랜덤 Pan·Zoom)
- 배경음악 다중 트랙 지원 (선택 UI, 드래그앤드롭 순서 변경, 이전/다음 곡)
- EXIF 메타데이터 전체 표시 (셔터·조리개·ISO·초점거리·플래시 등)
- 이미지 프리로드 (N+1, N+2 미리 로드, 메모리 자동 해제)
- 관리자 bcrypt 패스워드 해시 지원 (`ADMIN_PASSWORD_HASH`)
- Brute-force 방어 (5회 실패 시 15분 잠금)
- ZIP 다운로드 (앨범 전체 스트리밍)
- Docker 단일 컨테이너 구성 (FastAPI + Vanilla JS)

[Unreleased]: https://github.com/euikuk-jeong/lumisshow/compare/v0.8.1...HEAD
[0.8.1]: https://github.com/euikuk-jeong/lumisshow/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/euikuk-jeong/lumisshow/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/euikuk-jeong/lumisshow/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/euikuk-jeong/lumisshow/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/euikuk-jeong/lumisshow/compare/v0.5.2...v0.6.0
[0.5.2]: https://github.com/euikuk-jeong/lumisshow/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/euikuk-jeong/lumisshow/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/euikuk-jeong/lumisshow/compare/v0.4.3...v0.5.0
[0.4.3]: https://github.com/euikuk-jeong/lumisshow/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/euikuk-jeong/lumisshow/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/euikuk-jeong/lumisshow/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/euikuk-jeong/lumisshow/compare/v0.3.8...v0.4.0
[0.3.8]: https://github.com/euikuk-jeong/lumisshow/compare/v0.3.7...v0.3.8
[0.3.7]: https://github.com/euikuk-jeong/lumisshow/compare/v0.3.6...v0.3.7
[0.3.6]: https://github.com/euikuk-jeong/lumisshow/compare/v0.3.5...v0.3.6
[0.3.5]: https://github.com/euikuk-jeong/lumisshow/compare/v0.3.4...v0.3.5
[0.3.4]: https://github.com/euikuk-jeong/lumisshow/compare/v0.3.3...v0.3.4
[0.3.3]: https://github.com/euikuk-jeong/lumisshow/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/euikuk-jeong/lumisshow/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/euikuk-jeong/lumisshow/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/euikuk-jeong/lumisshow/compare/v0.2.6...v0.3.0
[0.2.6]: https://github.com/euikuk-jeong/lumisshow/compare/v0.2.5...v0.2.6
[0.2.5]: https://github.com/euikuk-jeong/lumisshow/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/euikuk-jeong/lumisshow/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/euikuk-jeong/lumisshow/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/euikuk-jeong/lumisshow/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/euikuk-jeong/lumisshow/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/euikuk-jeong/lumisshow/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/euikuk-jeong/lumisshow/releases/tag/v0.1.0
