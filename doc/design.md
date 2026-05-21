# mySlideshows - 상세 설계

## 1. 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    Synology NAS                              │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Docker Container                        │   │
│  │                                                      │   │
│  │  ┌─────────────┐    ┌──────────────────────────┐    │   │
│  │  │   Frontend  │    │    FastAPI Backend        │    │   │
│  │  │  (Static)   │◄───│  /api/*  REST API         │    │   │
│  │  │  HTML/CSS/JS│    │  /media/* 이미지 서빙      │    │   │
│  │  └─────────────┘    │  /thumb/* 썸네일 서빙      │    │   │
│  │                     └───────────┬──────────────┘    │   │
│  │                                 │                   │   │
│  │              ┌──────────────────┼──────────────┐    │   │
│  │              │                  │              │    │   │
│  │        ┌─────▼──────┐   ┌──────▼──────┐       │    │   │
│  │        │  SQLite DB │   │  Thumbnail  │       │    │   │
│  │        │  (data/db) │   │  Cache      │       │    │   │
│  │        └────────────┘   │  (data/thumb│       │    │   │
│  │                         └─────────────┘       │    │   │
│  └──────────────────────────────────────────────-┘   │   │
│                                                       │   │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  │   │
│  │ /volume1/    │  │ data/db/     │  │ data/music/│  │   │
│  │ photo/       │  │ app.db       │  │ *.mp3      │  │   │
│  │ (read-only   │  │ (read-write  │  │            │  │   │
│  │  volume)     │  │  volume)     │  │            │  │   │
│  └──────────────┘  └──────────────┘  └────────────┘  │   │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 데이터 모델

### 2.1 ERD

```
┌────────────────┐       ┌──────────────────┐       ┌─────────────────┐
│    albums      │       │  album_photos    │       │   share_links   │
├────────────────┤       ├──────────────────┤       ├─────────────────┤
│ id (PK)        │──┐    │ id (PK)          │    ┌──│ id (PK)         │
│ name           │  └───►│ album_id (FK)    │    │  │ album_id (FK)   │
│ description    │       │ file_path        │    │  │ token (UUID)    │
│ cover_photo_id │       │ sort_order       │    │  │ password_hash   │
│ music_path     │       │ added_at         │    │  │ expires_at      │
│ created_at     │       └──────────────────┘    │  │ created_at      │
│ updated_at     │◄──────────────────────────────┘  │ is_active       │
└────────────────┘                                   └─────────────────┘
```

### 2.2 테이블 스키마

```sql
CREATE TABLE albums (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    description TEXT,
    cover_path  TEXT,
    music_path  TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE album_photos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    album_id    INTEGER NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
    file_path   TEXT    NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    added_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(album_id, file_path)
);

CREATE TABLE share_links (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    album_id      INTEGER NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
    token         TEXT    NOT NULL UNIQUE,   -- UUID v4
    password_hash TEXT,                      -- bcrypt, NULL = no password
    expires_at    DATETIME,                  -- NULL = no expiry
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active     BOOLEAN  NOT NULL DEFAULT 1
);

CREATE TABLE thumbnail_cache (
    file_path     TEXT    PRIMARY KEY,
    thumb_path    TEXT    NOT NULL,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 3. API 설계

### 3.1 인증

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/auth/login` | Admin 로그인, JWT 반환 |
| POST | `/api/auth/logout` | 로그아웃 |
| GET  | `/api/auth/me` | 현재 세션 확인 |

**Request** `POST /api/auth/login`
```json
{ "password": "string" }
```
**Response**
```json
{ "access_token": "jwt_string", "token_type": "bearer" }
```

---

### 3.2 Admin - 파일 탐색

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/admin/browse` | 폴더 탐색 |
| GET | `/api/admin/search` | 이름/날짜/파일명으로 검색 |

**Query params** `GET /api/admin/browse`
```
path=string          # 탐색할 폴더 경로 (볼륨 루트 기준)
```

**Query params** `GET /api/admin/search`
```
q=string             # 파일명 검색어
date_from=YYYY-MM-DD
date_to=YYYY-MM-DD
folder=string        # 폴더 경로 필터
page=int
size=int
```

**Response** (공통)
```json
{
  "items": [
    {
      "path": "/volume1/photo/2024/trip/img001.jpg",
      "name": "img001.jpg",
      "size": 3145728,
      "taken_at": "2024-03-15T10:30:00",
      "width": 4000,
      "height": 3000,
      "thumb_url": "/thumb/abc123.jpg"
    }
  ],
  "total": 100,
  "page": 1
}
```

---

### 3.3 Admin - 앨범 관리

| Method | Path | 설명 |
|--------|------|------|
| GET    | `/api/admin/albums` | 앨범 목록 |
| POST   | `/api/admin/albums` | 앨범 생성 |
| GET    | `/api/admin/albums/{id}` | 앨범 상세 |
| PUT    | `/api/admin/albums/{id}` | 앨범 수정 |
| DELETE | `/api/admin/albums/{id}` | 앨범 삭제 |
| POST   | `/api/admin/albums/{id}/photos` | 사진 추가 |
| DELETE | `/api/admin/albums/{id}/photos` | 사진 제외 (batch) |
| PUT    | `/api/admin/albums/{id}/photos/order` | 순서 변경 |
| PUT    | `/api/admin/albums/{id}/music` | 배경음악 설정 |

**Request** `POST /api/admin/albums`
```json
{
  "name": "2024 제주도 여행",
  "description": "string",
  "photo_paths": ["/volume1/photo/2024/jeju/img001.jpg"]
}
```

**Request** `POST /api/admin/albums/{id}/photos`
```json
{
  "photo_paths": ["/volume1/photo/2024/jeju/img002.jpg"]
}
```

**Request** `DELETE /api/admin/albums/{id}/photos`
```json
{
  "photo_paths": ["/volume1/photo/2024/jeju/img001.jpg"]
}
```

---

### 3.4 Admin - 공유 링크 관리

| Method | Path | 설명 |
|--------|------|------|
| GET    | `/api/admin/albums/{id}/links` | 링크 목록 |
| POST   | `/api/admin/albums/{id}/links` | 링크 생성 |
| PUT    | `/api/admin/albums/{id}/links/{link_id}` | 링크 수정 |
| DELETE | `/api/admin/albums/{id}/links/{link_id}` | 링크 비활성화 |

**Request** `POST /api/admin/albums/{id}/links`
```json
{
  "password": "optional_string",
  "expires_at": "2025-12-31T23:59:59"
}
```

**Response**
```json
{
  "id": 1,
  "token": "550e8400-e29b-41d4-a716-446655440000",
  "share_url": "https://nas.local:8080/s/550e8400-e29b-41d4-a716-446655440000",
  "has_password": true,
  "expires_at": "2025-12-31T23:59:59"
}
```

---

### 3.5 공개 - 공유 링크 뷰어

| Method | Path | 설명 |
|--------|------|------|
| POST   | `/api/share/{token}/auth` | 패스워드 인증 |
| GET    | `/api/share/{token}` | 앨범 정보 조회 |
| GET    | `/api/share/{token}/photos` | 사진 목록 (페이징) |
| GET    | `/api/share/{token}/download` | 전체 ZIP 다운로드 |

**Request** `POST /api/share/{token}/auth`
```json
{ "password": "string" }
```
**Response**
```json
{ "session_token": "short_lived_jwt" }
```

**Response** `GET /api/share/{token}`
```json
{
  "album_name": "2024 제주도 여행",
  "description": "string",
  "photo_count": 42,
  "created_at": "2024-03-20T00:00:00",
  "expires_at": "2025-12-31T23:59:59",
  "has_music": true
}
```

**Response** `GET /api/share/{token}/photos`
```json
{
  "photos": [
    {
      "id": 1,
      "url": "/media/token/1",
      "thumb_url": "/thumb/token/1",
      "width": 4000,
      "height": 3000
    }
  ],
  "total": 42
}
```

---

### 3.6 미디어 서빙

| Method | Path | 설명 |
|--------|------|------|
| GET | `/thumb/{token}/{photo_id}` | 썸네일 이미지 |
| GET | `/media/{token}/{photo_id}` | 원본 이미지 |
| GET | `/media/{token}/{photo_id}/download` | 단일 이미지 다운로드 |
| GET | `/music/{token}` | 배경음악 파일 |

---

## 4. 화면 설계

### 4.1 화면 목록

```
┌─────────────────────────────────────────────────┐
│  공개 영역 (인증 불필요 or 링크 세션)             │
│  /s/{token}           링크 패스워드 입력          │
│  /s/{token}/view      앨범 메인 화면              │
│  /s/{token}/slideshow 슬라이드쇼                  │
├─────────────────────────────────────────────────┤
│  관리자 영역 (Admin JWT 필요)                     │
│  /admin/login         관리자 로그인               │
│  /admin/              앨범 목록 대시보드           │
│  /admin/albums/new    앨범 생성                   │
│  /admin/albums/{id}   앨범 편집                   │
│  /admin/browse        사진 탐색기                 │
└─────────────────────────────────────────────────┘
```

### 4.2 앨범 메인 화면 (`/s/{token}/view`)

```
┌──────────────────────────────────────────┐
│           [앨범 커버 이미지]               │
│                                          │
│         2024 제주도 여행                   │
│   여행의 추억을 담은 사진 모음입니다.        │
│                                          │
│   📷 42장   📅 2024-03-20                │
│   ⏰ 만료: 2025-12-31                    │
│                                          │
│  ┌──────────────┐  ┌──────────────┐      │
│  │ ▶ 슬라이드쇼  │  │ ⚙ 설정       │      │
│  └──────────────┘  └──────────────┘      │
│                                          │
│  ┌──────────────────────────────┐        │
│  │  ⬇ 전체 다운로드 (ZIP)       │        │
│  └──────────────────────────────┘        │
│                                          │
│  [썸네일 그리드 미리보기]                  │
└──────────────────────────────────────────┘
```

### 4.3 슬라이드쇼 설정 패널

```
┌─────────────────────────────┐
│  슬라이드쇼 설정             │
│                             │
│  전환 시간   [  5  ] 초      │
│                             │
│  순서        ○ 순서대로       │
│              ● 랜덤          │
│                             │
│  배경음악    [ON / OFF]      │
│  음량        [━━━●━━━━] 60% │
│                             │
│  전환 효과   ● 랜덤          │
│              ○ Fade          │
│              ○ Slide         │
│              ○ Zoom          │
│                             │
│    [취소]        [시작]       │
└─────────────────────────────┘
```

### 4.4 슬라이드쇼 화면

```
┌──────────────────────────────────────────────────┐
│ ←  [                                        ] →  │
│    [         이미지 (Ken Burns 효과)          ]   │
│    [                                         ]   │
│ ←  [                                        ] →  │
│                                                  │
│ ┌──────────────────────────────────────────────┐ │
│ │  ⏸  ◀◀  1 / 42  ▶▶  [⬇ 다운로드]  [✕ 닫기] │ │
│ └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

---

## 5. 슬라이드쇼 엔진 설계

### 5.1 전환 효과 목록

| 효과 ID | 이름 | 설명 |
|---------|------|------|
| `fade` | Fade | 현재 이미지 투명도 감소 → 다음 이미지 등장 |
| `slide-left` | Slide Left | 현재가 좌로 퇴장, 다음이 우에서 진입 |
| `slide-right` | Slide Right | 현재가 우로 퇴장, 다음이 좌에서 진입 |
| `slide-up` | Slide Up | 아래서 위로 |
| `zoom-in` | Zoom In | 다음 이미지가 중앙에서 확대되며 등장 |
| `zoom-out` | Zoom Out | 현재 이미지가 축소되며 퇴장 |
| `flip-h` | Flip H | 가로 플립 3D 효과 |
| `blur` | Blur | 현재 이미지 blur 후 다음 등장 |
| `dissolve` | Dissolve | 크로스 페이드 (두 이미지 동시 표시) |

### 5.2 Ken Burns 효과

슬라이드쇼 표시 중 이미지를 천천히 이동/확대하여 생동감 부여.

```
┌────────────────────────────┐
│    방향 벡터 랜덤 선택      │
│                            │
│  시작점 → 끝점 (8방향 중 1) │
│  ┌──────────────────────┐  │
│  │  ↗ ↑ ↖              │  │
│  │  →  ·  ←            │  │
│  │  ↘ ↓ ↙              │  │
│  └──────────────────────┘  │
│                            │
│  scale: 1.05 → 1.15 (랜덤) │
│  duration: 슬라이드 시간    │
│  easing: linear            │
└────────────────────────────┘
```

**CSS 구현 방식:**
```css
@keyframes kenburns-tl {
  from { transform: scale(1.05) translate(0%, 0%); }
  to   { transform: scale(1.15) translate(-3%, -3%); }
}
```
- 8개 방향 × scale 범위 = 랜덤 애니메이션 클래스 선택
- `animation-duration`은 슬라이드 전환 시간과 동일하게 설정

### 5.3 슬라이드쇼 상태 머신

```
        ┌─────────┐
        │  IDLE   │◄──────────────────────┐
        └────┬────┘                       │
             │ start()                    │
             ▼                            │
        ┌─────────┐  pause()   ┌──────────┴──┐
        │ PLAYING │◄──────────►│   PAUSED    │
        └────┬────┘  resume()  └─────────────┘
             │
             │ next() / prev() / auto-advance
             ▼
        ┌────────────┐
        │ TRANSITION │  (전환 효과 재생 중, ~800ms)
        └────┬───────┘
             │ 완료
             ▼
        ┌─────────┐
        │ PLAYING │ (다음 이미지 표시 + Ken Burns 시작)
        └─────────┘
```

### 5.4 이미지 프리로딩 전략

```
현재 표시: index N
프리로드:  index N+1, N+2
메모리 해제: index N-3 이전
```

---

## 6. 썸네일 생성 정책

| 구분 | 크기 | 용도 |
|------|------|------|
| Small thumb | 300×200 (fit) | 앨범 그리드, 탐색기 |
| Medium thumb | 800×600 (fit) | 슬라이드쇼 프리로드 |
| Original | 원본 | 슬라이드쇼 표시, 다운로드 |

- 최초 요청 시 생성, `data/thumbnails/` 에 저장
- 파일명: `MD5(file_path)_{size}.jpg`
- EXIF orientation 자동 보정

---

## 7. 보안 설계

### 7.1 인증 흐름

```
Admin:
  POST /api/auth/login {password}
  → JWT (HS256, exp: 8h) → Authorization: Bearer {jwt}
  → 모든 /api/admin/* 엔드포인트에서 검증

공유 링크 사용자:
  GET /s/{token}
  → token 유효성 + 만료일 검증
  → 패스워드 있으면 POST /api/share/{token}/auth
  → 단기 세션 쿠키 (httpOnly, SameSite=Strict, exp: 24h)
  → /media/{token}/*, /thumb/{token}/*, /music/{token} 접근 허용
```

### 7.2 환경변수 설정

```env
ADMIN_PASSWORD=secure_password      # Admin 패스워드 (bcrypt 해시로 저장)
JWT_SECRET=random_secret_key        # JWT 서명 키
APP_HOST=0.0.0.0
APP_PORT=8080
PHOTO_ROOT=/mnt/photos              # NAS 사진 볼륨 마운트 경로
DATA_DIR=/data                      # DB, 썸네일, 음악 저장 경로
BASE_URL=https://nas.example.com    # 공유 링크 생성 시 사용
```

---

## 8. Docker 구성

### 8.1 Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libexiv2-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/

EXPOSE 8080

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### 8.2 docker-compose.yml

```yaml
version: "3.9"

services:
  myslideshows:
    image: myslideshows:latest
    container_name: myslideshows
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      - /volume1/photo:/mnt/photos:ro        # NAS 사진 폴더 (읽기 전용)
      - /volume1/docker/myslideshows:/data   # 앱 데이터 (DB, 썸네일, 음악)
    environment:
      - ADMIN_PASSWORD=your_secure_password
      - JWT_SECRET=your_random_secret
      - PHOTO_ROOT=/mnt/photos
      - DATA_DIR=/data
      - BASE_URL=http://192.168.1.100:8080
```

---

## 9. Frontend 모듈 구조

```
frontend/
├── index.html              # 라우팅 진입점 (SPA)
├── assets/
│   ├── css/
│   │   ├── base.css
│   │   ├── slideshow.css   # 전환 효과 + Ken Burns keyframes
│   │   └── admin.css
│   └── js/
│       ├── router.js       # 클라이언트 사이드 라우팅
│       ├── api.js          # API 클라이언트
│       ├── auth.js         # JWT / 세션 관리
│       ├── pages/
│       │   ├── share-auth.js      # 패스워드 입력
│       │   ├── album-view.js      # 앨범 메인
│       │   ├── slideshow.js       # 슬라이드쇼 컨트롤러
│       │   ├── admin-login.js
│       │   ├── admin-albums.js
│       │   ├── admin-album-edit.js
│       │   └── admin-browse.js
│       └── components/
│           ├── transition-engine.js  # 전환 효과 적용
│           ├── kenburns.js           # Ken Burns 효과
│           ├── preloader.js          # 이미지 프리로드
│           ├── music-player.js       # 배경음악
│           └── settings-panel.js    # 슬라이드쇼 설정 UI
```

### 9.1 TransitionEngine 인터페이스

```javascript
class TransitionEngine {
  // 현재 이미지에서 다음 이미지로 전환
  async transition(fromEl, toEl, effect = 'random') { }
  
  // 사용 가능한 효과 목록
  static EFFECTS = ['fade', 'slide-left', 'slide-right', 'slide-up',
                    'zoom-in', 'zoom-out', 'flip-h', 'blur', 'dissolve'];
  
  // 랜덤 효과 선택
  static randomEffect() { }
}
```

### 9.2 KenBurns 인터페이스

```javascript
class KenBurns {
  // 이미지 엘리먼트에 랜덤 Ken Burns 적용
  apply(imgEl, duration) { }
  
  // 애니메이션 즉시 중단
  stop(imgEl) { }
}
```

### 9.3 슬라이드쇼 이벤트 처리

```javascript
// 키보드
document.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') slideshow.next();
  if (e.key === 'ArrowLeft'  || e.key === 'ArrowUp')   slideshow.prev();
  if (e.key === ' ')                                    slideshow.togglePause();
  if (e.key === 'Escape')                               slideshow.exit();
});

// 터치 스와이프
let touchStartX = 0;
el.addEventListener('touchstart', e => { touchStartX = e.touches[0].clientX; });
el.addEventListener('touchend',   e => {
  const dx = e.changedTouches[0].clientX - touchStartX;
  if (dx < -50) slideshow.next();
  if (dx >  50) slideshow.prev();
});
```

---

## 10. 성능 고려사항

| 항목 | 전략 |
|------|------|
| 대용량 이미지 로딩 | 썸네일 → 원본 순차 로드 (progressive) |
| ZIP 다운로드 | Python `zipfile` + `StreamingResponse` (서버 메모리 불사용) |
| 썸네일 생성 | 최초 요청 시 생성 + 디스크 캐시 (재시작 후에도 유지) |
| API 응답 | 사진 목록은 페이징 처리 (기본 100장/페이지) |
| 이미지 프리로드 | 현재 기준 앞 2장 미리 로드, 뒤 3장 메모리 해제 |
| 전환 효과 | CSS animation 우선 (GPU 가속), JS 보조 |

---

## 11. 오픈 이슈 및 결정 필요 사항

| # | 이슈 | 결정 / 옵션 | 우선순위 |
|---|------|-------------|----------|
| 1 | Frontend 프레임워크 | ✅ **Vanilla JS** 확정 (빌드 불필요, DOM 직접 제어, 슬라이드쇼 엔진 최적) | 완료 |
| 2 | 배경음악 자동재생 정책 | 첫 클릭 후 재생 시작 (브라우저 정책) | 중간 |
| 3 | 앨범 커버 선택 | 첫 번째 사진 자동 vs 수동 지정 | 낮음 |
| 4 | 관리자 다중 계정 | 현재 단일 Admin, 추후 확장 여부 | 낮음 |
| 5 | HTTPS 설정 | Reverse proxy (NAS DSM) 또는 내장 TLS | 중간 |
| 6 | 사진 정렬 기본값 | 촬영일 순 vs 파일명 순 | 낮음 |
