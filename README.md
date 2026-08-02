# LumisShow

Synology NAS용 Docker 기반 사진 앨범 & 슬라이드쇼 웹 앱.

단일 컨테이너로 FastAPI(백엔드) + Vanilla JS(프론트엔드)를 서빙하며, NAS 사진 폴더를 읽기 전용으로 마운트해 앨범을 구성하고 공유 링크로 배포합니다.

v1.0.0(Phase 2)부터는 별도 AI 워커 컨테이너(`lumisshow-ai`)가 NAS 로컬에서 얼굴 인식을 수행해, 사진 속 인물을 자동 분류하고 인물별 앨범·슬라이드쇼를 만들 수 있습니다. v2.0.0부터는 같은 AI 워커가 사물·장면·위치·폴더명까지 자동 태깅해, Admin에서 태그를 관리하고 XMP 사이드카로 내보낼 수도 있습니다. (외부 API 미사용 — 모든 분석은 NAS 안에서만 이루어집니다.)

---

## 프로젝트명 유래

프로젝트 초기 임시명은 `mySlideshows`였습니다. 정식 공개 전 여러 후보명을 검토하는 과정에서 **Lumis** (luminous·빛남에서 착안)가 유력 후보로 올랐으나, 동일 분야의 사진 앱 `lumisapp.com`과 충돌하여 제외되었습니다. 이어 검토한 **LumisShow**는 검색 결과에서 충돌이 없었고 "빛나는 슬라이드쇼"라는 의미도 잘 담겨 최종 프로젝트명으로 확정되었습니다.

---

## 주요 기능

### 관리자 (Admin)
- **사진 탐색** — NAS 사진 폴더를 트리 구조로 탐색, 파일명/태그 검색
- **앨범 관리** — 앨범 생성/편집/삭제, 사진 추가·제외
- **배경음악** — 앨범별 다중 음악 파일 설정, 드래그앤드롭으로 순서 변경
- **공유 링크** — 비밀번호·만료일 설정 가능한 공유 링크 생성

### 공유 링크 뷰어
- **패스워드 보호** — 비밀번호 설정 시 인증 후 접근 (Brute-force 잠금 포함)
- **앨범 보기** — 썸네일 그리드, 사진 클릭으로 전체화면 뷰어
- **ZIP 다운로드** — 앨범 전체 스트리밍 다운로드

### 슬라이드쇼
- **전환 효과 9종** — fade, slide, zoom, flip, blur, dissolve 등 랜덤/고정 선택
- **Ken Burns 효과** — 8방향 랜덤 Pan·Zoom 애니메이션
- **배경음악 플레이어**
  - 다중 트랙 지원 (이전곡·다음곡 버튼, 자동 다음 곡)
  - 음악 On/Off 토글, 음량 슬라이더
  - 트랙 변경 시 파일명 토스트 알림 (3초 후 자동 사라짐)
- **사진 정보 패널** — EXIF 전체 표시 (셔터·조리개·ISO·초점거리·플래시 등), 재생 중 음악 정보 함께 표시
- **이미지 프리로드** — N+1, N+2 이미지 미리 로드, 메모리 자동 해제

### AI 얼굴 인식 (Phase 2, v1.0.0+)
- **AI 워커 (`lumisshow-ai` 컨테이너)** — InsightFace(SCRFD 검출 + ArcFace 임베딩)로 사진 속 얼굴을 검출·매칭. 매일 야간 자동 증분 스캔 + Admin 수동 트리거, 중단 후 재개 가능
- **인물(People) 관리** — 인물 등록, AI 추정 얼굴 교정(맞음/아님), 미분류 얼굴 다중 선택 지정/무시 — 교정할수록 정확도 향상
- **인물 앨범 생성 도우미** — 인물 사진 전체를 앨범으로 생성 (공유 링크·슬라이드쇼·ZIP 등 기존 기능 그대로 사용)
- **인물 슬라이드쇼 · 전체 사진 보기** — 앨범 생성 없이 인물 상세에서 해당 인물 사진을 바로 슬라이드쇼 재생·그리드 탐색
- **로컬 처리** — 외부 API 없이 NAS 안에서만 분석. 모델 가중치(non-commercial)는 이미지에 미포함, 첫 실행 시 자동 다운로드

### AI 태그/위치/장면 인식 (v2.0.0+)
- **사물·장면 자동 태깅** — CLIP zero-shot(`clip-vit-base-patch32`)으로 82개 큐레이션 어휘(사람/구도·동물·음식·탈것·생활용품·자연/실외·실내장소·날씨·이벤트·액티비티) 중 매칭되는 태그를 사진마다 자동 부여
- **위치·폴더명 태깅** — EXIF GPS를 오프라인 리버스 지오코딩으로 도시/국가 태깅, 상위 폴더명은 한국어 형태소분석기(Kiwi)로 지명·이벤트명 등을 자동 태깅
- **Admin 태그 관리 화면** — 태그 목록(source별 필터·검색), 태그별 사진 그리드, 삭제/이름 일괄 변경, 수동 태그 추가(어휘 목록 중 선택)
- **소급 재계산(`tag-backfill`)** — 어휘·임계값을 바꿔도 이미 분석된 사진 전체에 CLI 또는 Admin 버튼으로 재적용
- **슬라이드쇼 정보 패널 태그 노출** — 인물·위치·태그·폴더명·수동 태그를 정보 패널(i 버튼)에 표시(공유 링크는 프라이버시 고려해 일부만 노출)
- **XMP 사이드카 export** — 태그·위치·확정 인물 전체를 사진별 `.xmp`로 묶어 원본과 동일한 폴더 구조 ZIP으로 다운로드(Lightroom·digiKam 등 외부 툴 호환), 원본 사진은 절대 수정하지 않음
- **로컬 처리** — GPS 역지오코딩·폴더명 형태소분석 모두 오프라인 패키지 사용, 외부 API 미사용

---

## 스크린샷 구성 (화면 설명)

| 화면 | 경로 | 설명 |
|------|------|------|
| Admin 로그인 | `/admin/login` | JWT 인증 |
| 앨범 목록 | `/admin` | 앨범 카드 그리드 |
| 앨범 편집 | `/admin/albums/:id` | 사진·음악·공유링크 관리 |
| 사진 탐색 | `/admin/browse` | 폴더 트리 + 다중 선택 |
| 인물 목록 | `/admin/people` | 인물 카드 + AI 분석 상태·스캔 트리거 |
| 인물 상세 | `/admin/people/:id` | 얼굴 교정, 미분류 지정, 앨범 생성 |
| 인물 전체 사진 | `/admin/people/:id/photos` | 인물 사진 그리드 + 슬라이드쇼 |
| 태그 관리 | `/admin/tags` | 태그 목록·사진 그리드, 수동 태그 추가 |
| 공유 뷰어 | `/s/:token` | 패스워드 입력 → 앨범 |
| 슬라이드쇼 | `/s/:token/slideshow` | 전체화면 슬라이드쇼 |

---

## 빠른 시작 (Docker)

### 1. 이미지 준비

**권장 — GHCR 사전 빌드 이미지 사용:**

```bash
docker pull ghcr.io/euikuk-jeong/lumisshow:latest
docker pull ghcr.io/euikuk-jeong/lumisshow-ai:latest   # AI 얼굴 인식 사용 시
```

**직접 빌드 (개발/커스터마이즈):**

```bash
git clone https://github.com/euikuk-jeong/lumisshow.git
cd lumisshow
docker build -f docker/Dockerfile -t ghcr.io/euikuk-jeong/lumisshow:latest .
```

### 2. 환경변수 설정

```bash
cp .env.example .env
# .env를 열어 아래 값 설정
```

```dotenv
# 관리자 패스워드 — 둘 중 하나만 설정
ADMIN_PASSWORD=your_secure_password       # 개발/테스트용 평문
# ADMIN_PASSWORD_HASH=$2b$12$...         # 운영 권장: bcrypt 해시

JWT_SECRET=<openssl rand -hex 32 출력값>
PHOTO_ROOT=/mnt/photos                   # 컨테이너 내부 경로
DATA_DIR=/data
BASE_URL=http://192.168.1.100:8080
APP_PORT=8080
```

bcrypt 해시 생성:
```bash
python3 -c "import bcrypt; print(bcrypt.hashpw(b'your_password', bcrypt.gensalt()).decode())"
```

### 3. 실행

```bash
docker compose -f docker/docker-compose.yml up -d
```

브라우저에서 `http://localhost:8080/admin` 접속 후 로그인.

> **Synology Container Manager에서 GHCR 이미지를 처음 사용할 때:**
> GitHub → Packages → lumisshow → Package settings → **"Change visibility" → Public** 으로 변경해야 인증 없이 pull할 수 있어요. (최초 1회)

---

## 환경변수

| 변수 | 필수 | 설명 |
|------|------|------|
| `ADMIN_PASSWORD` | △ | 관리자 평문 패스워드 (개발용) |
| `ADMIN_PASSWORD_HASH` | △ | 관리자 bcrypt 해시 (운영 권장, 설정 시 ADMIN_PASSWORD 무시) |
| `JWT_SECRET` | ✓ | JWT 서명 키 (32바이트 이상 랜덤값 권장) |
| `PHOTO_ROOT` | ✓ | NAS 사진 폴더 마운트 경로 (컨테이너 내부) |
| `DATA_DIR` | ✓ | DB·썸네일·음악 저장 경로 (컨테이너 내부) |
| `BASE_URL` | | 공유 링크 URL 생성 베이스 주소 |
| `APP_PORT` | | 서버 포트 (기본 `8080`) |
| `TZ` | | AI 워커 야간 스캔 시각 기준 타임존 (기본 `Asia/Seoul`) |
| `AI_SCAN_HOUR` | | AI 워커 야간 자동 스캔 시각 0~23 (기본 `2`) |
| `AI_MATCH_THRESHOLD` | | 얼굴 매칭 cosine 임계값 (기본 `0.45`) |
| `AI_TAG_THRESHOLD` | | AI 태그(CLIP zero-shot) 부여 cosine 임계값 (기본 `0.24`) |

`ADMIN_PASSWORD` 또는 `ADMIN_PASSWORD_HASH` 중 하나는 반드시 설정해야 합니다.

---

## 배경음악 설정

1. 음악 파일(`.mp3`, `.flac`, `.ogg`, `.m4a`, `.wav` 등)을 `DATA_DIR/music/` 폴더에 복사
2. Admin → 앨범 편집 → **배경음악** 섹션 → **음악 파일 선택** 버튼
3. 체크박스로 다중 선택 후 확인
4. 목록에서 드래그앤드롭으로 재생 순서 변경
5. 저장

슬라이드쇼 재생 중 툴바 왼쪽의 음악 컨트롤로 On/Off, 이전/다음 곡 조작 가능.

---

## 데이터 구조 (DATA_DIR)

```
$DATA_DIR/
├── db/
│   ├── app.db          # SQLite — 앨범, 사진, 공유링크
│   └── ai.db           # SQLite — 얼굴 인식 결과·인물·라벨, 태그·위치·이미지 임베딩 (AI 워커)
├── thumbnails/          # on-demand 생성 썸네일 캐시
├── music/              # 배경음악 파일
└── models/             # InsightFace 모델 가중치 (첫 실행 시 자동 다운로드)
```

---

## Synology NAS 배포

### 최초 설치

1. NAS SSH에서 환경변수 파일 준비:

```bash
mkdir -p /volume1/docker/lumisshow-config
cat > /volume1/docker/lumisshow-config/.env <<'EOF'
ADMIN_PASSWORD_HASH=$2b$12$...   # bcrypt 해시 (권장)
JWT_SECRET=<openssl rand -hex 32 출력값>
BASE_URL=http://192.168.1.100:8080
APP_PORT=8080
EOF
```

2. Container Manager → 레지스트리 → `ghcr.io/euikuk-jeong/lumisshow:latest` 이미지 다운로드

3. `docker/docker-compose.yml`로 스택 실행:
   - `/volume1/photo` → `/mnt/photos` (읽기 전용)
   - `/volume1/docker/lumisshow` → `/data`
   - `lumisshow-ai` 서비스 포함 (`mem_limit 2g`, 사진 볼륨 읽기 전용 공유) — AI 기능을 사용하지 않으면 해당 서비스를 제거해도 됩니다

4. DSM 리버스 프록시로 HTTPS 적용 (선택)

### 새 버전 업데이트

```bash
# SSH 또는 Container Manager 터미널에서
docker compose -f /path/to/docker-compose.yml pull
docker compose -f /path/to/docker-compose.yml up -d
```

또는 Container Manager UI에서 **스택 → 업데이트** 클릭.

> **데이터 유지:** `/volume1/docker/lumisshow`가 외부 볼륨으로 마운트되어 있으면 업데이트 후에도 DB·썸네일·음악이 그대로 유지돼요.

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| Backend | Python 3.12, FastAPI, aiosqlite (SQLite), Pillow |
| Frontend | Vanilla JS (ES Modules), 빌드 도구 없음 |
| AI Worker | InsightFace buffalo_l (SCRFD 검출 + ArcFace 512-d 임베딩), ONNX Runtime, numpy cosine 매칭 |
| Auth | JWT (python-jose), bcrypt, httpOnly 세션 쿠키 |
| Container | Docker — 앱 컨테이너(FastAPI가 정적파일 서빙) + AI 워커 컨테이너(선택) |

---

## 보안

- Admin 패스워드: bcrypt 해시 저장 지원 (`ADMIN_PASSWORD_HASH`)
- JWT: 8시간 만료, 안전한 서명 키 필수
- 공유 링크: UUID v4 토큰, httpOnly 세션 쿠키 (24시간)
- 미디어 접근: 세션 쿠키 검증 + 앨범 소속 여부 확인 + `PHOTO_ROOT` 경로 이탈 방지
- 음악 파일: `DATA_DIR/music/` 범위 이탈 방지
- Brute-force 방어: 5회 실패 시 15분 잠금

---

## 라이선스

MIT
