# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/euikuk-jeong/lumisshow/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/euikuk-jeong/lumisshow/releases/tag/v0.1.0
