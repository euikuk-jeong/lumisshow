# docker/CLAUDE.md

Docker 빌드·배포 상세 컨텍스트. 루트 → [`/CLAUDE.md`](../CLAUDE.md)

---

## 빌드 & 실행 명령

환경변수 설정은 루트의 `.env.example`을 복사해 `.env`로 사용한다. `ADMIN_PASSWORD`와 `JWT_SECRET`은 필수값 — 누락 시 컨테이너 시작 실패.

```bash
# 이미지 빌드
docker build -f docker/Dockerfile -t lumisshow:latest .

# 로컬 컨테이너 실행 (.env 파일 필요)
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
