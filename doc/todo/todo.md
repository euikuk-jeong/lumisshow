# Todo

## 미완료

- [x] serve_media/serve_thumb PHOTO_ROOT containment check 추가 (serve_music과 동일한 realpath+startswith 방어) <!-- 2026-05-31 완료 -->
- [x] 공유 링크 패스워드 브루트포스 방어: 토큰별 실패 횟수 추적, 5회 실패 시 일시 잠금 <!-- 2026-05-31 완료 -->
- [x] admin-albums.js:39, admin-album-edit.js:83 — innerHTML에 esc(e.message) 적용 (admin-browse.js 2곳, router.js 1곳도 함께 수정) <!-- 2026-05-31 완료 -->
- [ ] Admin UI 수동 테스트 및 버그 수정 <!-- 2026-05-29 추가 -->
- [x] Synology 배포 가이드 작성 (docker-compose 예시, 환경변수, 볼륨 설명) <!-- 2026-05-31 완료 -->
- [ ] Phase 4 슬라이드쇼 개선: EFFECTS 배열 3-way sync 자동화, loadSettings 공유 모듈화, ?i=N URL 재생 중 정리 <!-- 2026-05-29 추가 -->
- [x] Admin Browse → Album 사진 추가 시 절대 경로 처리 버그 수정 (상대경로 → PHOTO_ROOT 결합) <!-- 2026-05-31 완료 -->

## 완료

- [x] Frontend Phase 4 - 슬라이드쇼 구현 + 코드 리뷰 + 버그 수정 3건 <!-- 2026-05-29 완료 -->
- [x] Phase 3 공유 링크 뷰어 코드 리뷰 및 5건 수정 <!-- 2026-05-29 완료 -->
- [x] Frontend Phase 3 - 공유 링크 뷰어 (패스워드 입력, 앨범 메인, ZIP 다운로드) <!-- 2026-05-29 완료 -->
- [x] Phase 2 Admin UI 코드 리뷰 및 9건 수정 <!-- 2026-05-29 완료 -->
- [x] Frontend SPA 구현 Phase 2 - Admin UI (로그인, 앨범 관리, 사진 탐색, 공유 링크) <!-- 2026-05-29 완료 -->
- [x] 공개 공유 링크 뷰어 API (`routers/share.py`) + 단위 테스트 <!-- 2026-05-28 완료 -->
- [x] 미디어 서빙 API (`routers/media.py`: /thumb/, /media/, /music/) + 단위 테스트 <!-- 2026-05-28 완료 -->
- [x] E2E 테스트 설정 및 수행 (Playwright 또는 pytest + 실서버 기반, 주요 사용자 플로우 커버) <!-- 2026-05-28 완료 -->
- [x] Docker 패키징 (Dockerfile, docker-compose.yml) <!-- 2026-05-28 완료 -->
- [x] 공유 링크 관리 API 구현 (`routers/admin_links.py`) + 단위 테스트 <!-- 2026-05-28 완료 -->
- [x] 앨범 CRUD API 구현 (`routers/admin_albums.py`) + 단위 테스트 <!-- 2026-05-28 완료 -->
- [x] Python 개발 환경 설정 (.venv, requirements.txt, pytest.ini) <!-- 2026-05-26 완료 -->
- [x] phase1 브랜치 생성 및 GitHub push <!-- 2026-05-26 완료 -->
- [x] SQLite 데이터 모델 구현 (database.py: 4개 테이블 DDL) <!-- 2026-05-26 완료 -->
- [x] Pydantic 스키마 전체 작성 (schemas.py) <!-- 2026-05-26 완료 -->
- [x] Admin 인증 구현 (JWT HS256, bcrypt, 의존성) <!-- 2026-05-26 완료 -->
- [x] 파일 탐색 API 구현 (/browse, /search, /thumb) <!-- 2026-05-26 완료 -->
- [x] 썸네일 서비스 구현 (Pillow, EXIF 파싱, 캐시) <!-- 2026-05-26 완료 -->
- [x] 단위 테스트 36개 작성 및 all pass 확인 <!-- 2026-05-26 완료 -->
