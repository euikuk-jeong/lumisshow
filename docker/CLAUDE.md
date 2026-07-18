# docker/CLAUDE.md

Docker 빌드·배포 상세 컨텍스트. 루트 → [`/CLAUDE.md`](../CLAUDE.md)

---

## 빌드 & 실행 명령

환경변수 설정은 루트의 `.env.example`을 복사해 `.env`로 사용한다. `ADMIN_PASSWORD`와 `JWT_SECRET`은 필수값 — 누락 시 컨테이너 시작 실패.

```bash
# 이미지 빌드 (개발용 로컬 빌드)
docker build -f docker/Dockerfile -t ghcr.io/euikuk-jeong/lumisshow:latest .

# AI 워커 이미지 빌드 (Phase 2)
docker build -f docker/Dockerfile.ai -t ghcr.io/euikuk-jeong/lumisshow-ai:latest .

# 로컬 컨테이너 실행 (.env 파일 필요)
docker compose -f docker/docker-compose.yml up -d

# GHCR에서 최신 이미지 pull 후 재시작 (운영 업데이트)
docker compose -f docker/docker-compose.yml pull
docker compose -f docker/docker-compose.yml up -d

# 로그 확인 (container_name: lumisshow)
docker logs -f lumisshow

# 컨테이너 재시작 없이 코드 반영 (개발 중)
docker compose -f docker/docker-compose.yml restart
```

---

## 환경변수

| 변수 | 설명 | 예시 |
|------|------|------|
| `ADMIN_PASSWORD` | Admin 로그인 평문 패스워드 (개발용) | `secure_pass` |
| `ADMIN_PASSWORD_HASH` | Admin bcrypt 해시 (운영 권장, 설정 시 `ADMIN_PASSWORD` 무시) | `$2b$12$...` |
| `JWT_SECRET` | JWT 서명 키 (충분한 랜덤 값) | `openssl rand -hex 32` |
| `PHOTO_ROOT` | NAS 사진 폴더 마운트 경로 | `/mnt/photos` |
| `DATA_DIR` | DB/썸네일/음악 저장 경로 | `/data` |
| `BASE_URL` | 공유 링크 URL 생성용 베이스 | `http://192.168.1.100:8080` |
| `APP_PORT` | 서버 포트 (기본 8080) | `8080` |
| `THUMB_MAX_CONCURRENCY` | 동시 썸네일 생성(원본 디코딩) 최대 개수 — NAS 메모리 스파이크 방지 (기본 4) | `4` |
| `EXIF_READ_CONCURRENCY` | photo_meta_cache 미스 시 동시 EXIF 읽기 최대 개수 — search 날짜 필터 등 대량 미스 시 NAS I/O 폭주 방지 (기본 8) | `8` |
| `PUID` / `PGID` | 비-root 실행 시 사용할 UID/GID (선택, 미설정 시 root로 실행) | `1000` |

### AI 워커 (lumisshow-ai) 전용

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `TZ` | 야간 스캔 시각의 기준 타임존 | `Asia/Seoul` (compose) |
| `AI_SCAN_HOUR` | 야간 자동 스캔 시각 (0~23) | `2` |
| `AI_MATCH_THRESHOLD` | 얼굴 매칭 cosine 임계값 (eval로 튜닝된 값) | `0.45` |
| `AI_DET_SIZE` | SCRFD 검출 입력 크기 (RAM 부족 시 480으로 축소) | `640` |
| `AI_POLL_INTERVAL` | jobs 큐 폴링 간격(초) | `30` |
| `AI_MODEL_ROOT` | InsightFace 가중치 저장 경로 | `$DATA_DIR/models` |

- 모델 가중치(buffalo_l, 약 300MB)는 non-commercial 라이선스라 이미지에 포함하지 않으며,
  첫 스캔 시 `$DATA_DIR/models/`로 자동 다운로드된다 (볼륨 영속 → 재시작 시 재다운로드 없음).
- `mem_limit: 2g`로 분석 중 메모리 스파이크가 DSM/웹앱에 번지지 않게 제한한다.
- 릴리즈 태그 push 시 `lumisshow`와 `lumisshow-ai` 이미지가 함께 빌드·배포된다 (release.yml).
- 개발 브랜치에 ai_worker/backend/docker 변경 push 시 빌드 검증만 수행 (docker-build-check.yml).

`ADMIN_PASSWORD`와 `ADMIN_PASSWORD_HASH` 중 하나는 반드시 설정해야 한다. bcrypt 해시 생성:
```bash
python3 -c "import bcrypt; print(bcrypt.hashpw(b'your_password', bcrypt.gensalt()).decode())"
```

---

## 비-root 실행 (PUID/PGID)

기본값은 root 실행(하위 호환). 컨테이너를 비-root로 돌리려면 `PHOTO_ROOT`를 읽을 수 있는 계정의 UID/GID를 `.env`에 지정한다.

```bash
# NAS에서 PHOTO_ROOT 소유 계정 확인
stat /volume1/photo
# Uid: (138862/PhotoStation)   Gid: (138862/PhotoStation)

# .env
PUID=138862
PGID=138862
```

- `lumisshow`, `lumisshow-ai` 두 컨테이너가 `/data`를 공유하므로 **반드시 동일한 PUID/PGID**를 사용해야 한다. 값이 다르면 한쪽이 만든 파일을 다른 쪽이 못 읽는 문제가 생긴다.
- entrypoint(`docker/entrypoint.sh`)가 컨테이너 시작마다 `/data` 소유권을 확인하고, `PUID:PGID`와 다를 때만 `chown -R`을 수행한다. 즉 **재귀 chown은 이 값을 처음 설정한 직후 1회만** 발생하고, 이후 재기동부터는 소유권이 이미 맞아 즉시 스킵된다. 파일이 많으면(썸네일·얼굴 크롭 캐시) 최초 1회에 한해 시작이 다소 지연될 수 있다.
- `PHOTO_ROOT`(`:ro` 마운트)는 chown 대상이 아니다 — 원본 사진은 절대 건드리지 않는다.
- 값을 바꾸는 경우(예: 138862 → 다른 값)에도 위 로직대로 다음 시작 시 자동으로 재-chown된다.
- entrypoint는 `/data` **최상위 디렉토리 소유권만 보고** 일치 여부를 판단한다. `/data`를 수동으로 최상위만 `chown`해두면 하위 파일은 여전히 이전 소유자로 남아 재귀 chown이 스킵되니, 소유권 변경은 이 entrypoint에 맡기고 수동 chown은 하지 않는다.
- `APP_PORT`를 1024 미만으로 바꾸면 비-root 프로세스는 해당 포트에 bind할 수 없다. 기본값(8080)은 문제없다.

---

## Synology 배포 시 주의사항

- `PHOTO_ROOT` 볼륨은 반드시 `:ro`(read-only)로 마운트. 원본 사진 폴더를 절대 수정하지 않음.
- `DATA_DIR` 볼륨은 컨테이너 외부에 마운트해야 재시작 후에도 DB와 썸네일 캐시가 유지됨.
- Synology Container Manager는 docker-compose v2 기반이므로 `version:` 필드 없이도 동작.
- HTTPS는 DSM의 Reverse Proxy(Application Portal)를 통해 처리하는 것을 권장.

---

## 쿠키 보안 참고사항

`share_session` 및 `admin_img_session` 쿠키의 `Secure` 속성은 `BASE_URL` 환경변수를 기준으로 결정된다.

**핵심**: 앱 자체가 HTTP로 동작하더라도 `BASE_URL`을 공개 HTTPS URL로 설정해야 `Secure` 플래그가 활성화된다.

```
# 올바른 설정 (DSM Reverse Proxy 뒤에서 HTTPS 서비스하는 경우)
BASE_URL=https://your.domain.com

# 잘못된 설정 — TLS 연결이어도 Secure 플래그 없이 쿠키 발급됨
BASE_URL=http://192.168.1.100:8080
```

### Admin 로그인 속도 제한

동일 IP에서 5회 연속 로그인 실패 시 15분간 해당 IP의 로그인이 차단된다 (`share_link_failures` 테이블 재사용, `admin:{ip}` 키).

**주의**: DSM Reverse Proxy 뒤에서는 모든 클라이언트 IP가 프록시 IP(예: `127.0.0.1`)로 단일화될 수 있어, 속도 제한이 사실상 전역으로 동작한다. 이 경우 DSM 방화벽 또는 Reverse Proxy의 요청 속도 제한 기능을 함께 사용할 것을 권장한다.
