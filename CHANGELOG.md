# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/euikuk-jeong/lumisshow/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/euikuk-jeong/lumisshow/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/euikuk-jeong/lumisshow/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/euikuk-jeong/lumisshow/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/euikuk-jeong/lumisshow/releases/tag/v0.1.0
