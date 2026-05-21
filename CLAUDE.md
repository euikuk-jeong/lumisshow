# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Synology NAS용 Docker 기반 사진 앨범 & 슬라이드쇼 웹 앱. 단일 컨테이너로 FastAPI(backend) + Vanilla JS(frontend)를 서빙하며, NAS 사진 폴더를 읽기 전용 볼륨으로 마운트해 앨범을 구성하고 공유 링크로 배포한다.

전체 요구사항 → `doc/plan.md` / 상세 설계(API, ERD, 화면, 슬라이드쇼 엔진) → `doc/design.md`

---

## Development Commands

### 로컬 개발 (코드 작성 후)

```bash
# 의존성 설치
pip install -r backend/requirements.txt

# 개발 서버 실행 (hot-reload)
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8080

# 환경변수 (개발용)
export ADMIN_PASSWORD=dev_password
export JWT_SECRET=dev_secret_key
export PHOTO_ROOT=./testdata/photos   # 로컬 테스트 사진 경로
export DATA_DIR=./testdata/data
export BASE_URL=http://localhost:8080
```

### Docker 빌드 & 실행

```bash
# 이미지 빌드
docker build -f docker/Dockerfile -t myslideshows:latest .

# 로컬 컨테이너 실행
docker compose -f docker/docker-compose.yml up -d

# 로그 확인
docker logs -f myslideshows

# 컨테이너 재시작 없이 코드 반영 (개발 중)
docker compose -f docker/docker-compose.yml restart
```

---

## Architecture

### 요청 흐름

```
Browser → FastAPI (port 8080)
         ├── /            → frontend/index.html (SPA 진입점)
         ├── /assets/*    → frontend/assets/ (정적 파일)
         ├── /api/*       → REST API (인증 필요)
         ├── /s/{token}   → SPA 라우트 (공유 링크 뷰어)
         ├── /thumb/*     → 썸네일 (링크 세션 쿠키 검증)
         ├── /media/*     → 원본 이미지 (링크 세션 쿠키 검증)
         └── /music/*     → 배경음악 (링크 세션 쿠키 검증)
```

### 인증 이중 구조

- **Admin**: JWT Bearer 토큰 (exp 8h) → `/api/admin/*` 전체 보호
- **공유 링크 사용자**: UUID 토큰으로 앨범 접근 → 패스워드 입력 후 httpOnly 세션 쿠키 발급 (exp 24h) → `/media/`, `/thumb/`, `/music/` 접근 허용

### 데이터 영속성

- `$DATA_DIR/db/app.db` — SQLite (albums, album_photos, share_links, thumbnail_cache)
- `$DATA_DIR/thumbnails/` — `MD5(file_path)_{size}.jpg` 형식 캐시 (재시작 후에도 유지)
- `$DATA_DIR/music/` — 배경음악 파일
- `$PHOTO_ROOT` — NAS 원본 사진 (읽기 전용, 절대 수정하지 않음)

### Backend 구조 (`backend/`)

```
main.py              # FastAPI app, 미들웨어, 라우터 등록
routers/
  auth.py            # POST /api/auth/login|logout, GET /api/auth/me
  admin_browse.py    # GET /api/admin/browse|search
  admin_albums.py    # CRUD /api/admin/albums/*
  admin_links.py     # CRUD /api/admin/albums/{id}/links
  share.py           # GET|POST /api/share/{token}/*
  media.py           # /thumb/, /media/, /music/ 서빙
models/
  database.py        # SQLite 연결, 테이블 생성
  schemas.py         # Pydantic 요청/응답 모델
services/
  thumbnail.py       # Pillow 썸네일 생성, EXIF 보정
  auth.py            # JWT 생성/검증, bcrypt 해시
  zip_stream.py      # 스트리밍 ZIP 생성
```

### Frontend 구조 (`frontend/`)

```
index.html                     # SPA 진입점, 클라이언트 라우팅
assets/js/
  router.js                    # URL 기반 페이지 전환
  api.js                       # fetch 래퍼, 토큰 자동 첨부
  auth.js                      # JWT 로컬스토리지, 쿠키 관리
  pages/                       # 각 화면 진입점
  components/
    transition-engine.js       # 9가지 전환 효과 (CSS animation)
    kenburns.js                # Ken Burns 8방향 랜덤 이동
    preloader.js               # N+1, N+2 이미지 프리로드
    music-player.js            # Audio API, loop, 음량
    settings-panel.js          # 슬라이드쇼 설정 UI
assets/css/
  slideshow.css                # 전환 효과 keyframes + Ken Burns keyframes
```

---

## Key Design Decisions

### 슬라이드쇼 전환 효과
CSS animation 우선(GPU 가속). `transition-engine.js`의 `TransitionEngine.EFFECTS` 배열에서 랜덤 선택. 수동 이동(화살표/키보드/스와이프)도 동일한 효과 경로를 통과한다 — 별도 분기 없음.

### Ken Burns 효과
8개 방향 CSS `@keyframes` 사전 정의(`slideshow.css`), JS에서 랜덤 클래스 부착. `animation-duration`을 슬라이드 전환 시간과 동일하게 동적 설정. `scale` 범위: 1.05 → 1.15.

### 이미지 프리로드
현재 index N 표시 중 N+1, N+2 미리 로드. N-3 이전 `img.src = ''`으로 메모리 해제. `preloader.js`가 상태 관리.

### ZIP 다운로드
`StreamingResponse` + `zipfile.ZipFile` 스트리밍으로 서버 메모리에 전체 파일을 올리지 않음. 응답 헤더에 `Content-Disposition: attachment` 설정.

### 썸네일
두 가지 크기 — small(300×200, 그리드/탐색기), medium(800×600, 슬라이드쇼 프리로드). 최초 요청 시 on-demand 생성. EXIF orientation 자동 보정 필수(`Pillow`의 `ImageOps.exif_transpose`).

### 공유 링크 토큰
UUID v4. 브루트포스 불가 수준의 랜덤성. 만료일(`expires_at`)과 활성화 플래그(`is_active`)를 모두 확인해야 유효.

### 배경음악 자동재생
브라우저 정책 상 첫 사용자 제스처(슬라이드쇼 시작 버튼 클릭) 이후에만 `audio.play()` 호출. 설정 패널의 ON/OFF 상태를 `localStorage`에 저장해 새로고침 후에도 유지.

---

## Environment Variables

| 변수 | 설명 | 예시 |
|------|------|------|
| `ADMIN_PASSWORD` | Admin 로그인 패스워드 | `secure_pass` |
| `JWT_SECRET` | JWT 서명 키 (충분한 랜덤 값) | `openssl rand -hex 32` |
| `PHOTO_ROOT` | NAS 사진 폴더 마운트 경로 | `/mnt/photos` |
| `DATA_DIR` | DB/썸네일/음악 저장 경로 | `/data` |
| `BASE_URL` | 공유 링크 URL 생성용 베이스 | `http://192.168.1.100:8080` |
| `APP_PORT` | 서버 포트 (기본 8080) | `8080` |

---

## Synology 배포 시 주의사항

- `PHOTO_ROOT` 볼륨은 반드시 `:ro`(read-only)로 마운트. 원본 사진 폴더를 절대 수정하지 않음.
- `DATA_DIR` 볼륨은 컨테이너 외부에 마운트해야 재시작 후에도 DB와 썸네일 캐시가 유지됨.
- Synology Container Manager는 docker-compose v2 기반이므로 `version:` 필드 없이도 동작.
- HTTPS는 DSM의 Reverse Proxy(Application Portal)를 통해 처리하는 것을 권장.

## Git Rules

- `doc/context/` 하위 세션 요약 `.md` 파일은 git에 포함한다.
- `CHANGELOG.md`, `README.md` 등 프로젝트 문서 `.md` 파일도 git에 포함한다.
- When staging files, always include `doc/context/*.md` and project `.md` files.

## Todo 관리 규칙

대화 중 발생하는 할 일·아이디어·개선 사항은 `doc/todo/todo.md` 파일로 관리한다.

### Todo 추가 시점
- 대화 중 "나중에", "다음에", "추후", "TODO", "개선 필요" 등의 표현이 나올 때
- 분석 결과 수정이 필요하지만 현재 세션에서 처리하지 않기로 한 항목
- 사용자가 명시적으로 todo로 남겨달라고 요청할 때

### todo.md 형식

```markdown
# Todo

## 미완료

- [ ] 항목 설명 <!-- YYYY-MM-DD 추가 -->

## 완료

- [x] 항목 설명 <!-- YYYY-MM-DD 완료 -->
```

- 날짜는 `<!-- YYYY-MM-DD -->` 주석 형식으로 줄 끝에 표기
- 새 항목은 "미완료" 섹션 맨 위에 추가
- `doc/todo/` 디렉토리가 없으면 생성 후 파일 작성

### Git Rules (todo)
- `doc/todo/todo.md` 파일은 git에 포함한다.
- When staging files, always include `doc/todo/todo.md`.

## 세션 종료 규칙

사용자가 "종료", "끝", "bye", "exit", "마무리" 등 세션을 마치려는 의사를 표현하면:

1. 현재 대화에서 수행한 주요 작업을 한국어로 요약
2. 파일명 형식: `doc/context/YYYYMMDD_HHMM_요약제목.md`
   - 날짜/시간은 실제 현재 시각 사용
   - 요약제목은 작업 내용을 2~4단어로 압축
3. 파일 내용 구성:
   - 날짜/시간
   - 작업 목록 (bullet points)
   - 주요 결정 사항 또는 변경 내용
   - 미완료 작업 또는 다음 단계 (있을 경우)
4. `doc/todo/todo.md` 확인 후 이번 세션에서 완료한 항목을 `[x]`로 표시하고 완료 날짜 주석을 추가
5. 파일 저장 후 경로를 사용자에게 알림