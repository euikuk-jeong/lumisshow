# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/euikuk-jeong/lumisshow/compare/v0.3.1...HEAD
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
