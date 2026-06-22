# docker/CLAUDE.md

Docker 빌드·배포 상세 컨텍스트. 루트 → [`/CLAUDE.md`](../CLAUDE.md)

---

## 빌드 & 실행 명령

환경변수 설정은 루트의 `.env.example`을 복사해 `.env`로 사용한다. `ADMIN_PASSWORD`와 `JWT_SECRET`은 필수값 — 누락 시 컨테이너 시작 실패.

```bash
# 이미지 빌드 (개발용 로컬 빌드)
docker build -f docker/Dockerfile -t ghcr.io/euikuk-jeong/lumisshow:latest .

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

`ADMIN_PASSWORD`와 `ADMIN_PASSWORD_HASH` 중 하나는 반드시 설정해야 한다. bcrypt 해시 생성:
```bash
python3 -c "import bcrypt; print(bcrypt.hashpw(b'your_password', bcrypt.gensalt()).decode())"
```

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
