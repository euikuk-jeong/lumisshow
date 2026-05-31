# LumisShow — Synology NAS 배포 가이드

## 사전 요구사항

- DSM 7.2 이상
- **Container Manager** 패키지 설치 (패키지 센터에서 설치)
- SSH 접속 가능 (또는 Container Manager GUI만으로도 배포 가능)
- 사진 폴더가 `/volume1/photo` 등으로 접근 가능한 상태

---

## 1. 폴더 준비

FileStation 또는 SSH에서 데이터 폴더를 생성합니다.

```bash
# SSH 접속 후
mkdir -p /volume1/docker/lumisshow
```

- `/volume1/photo` — 기존 사진 폴더 (읽기 전용으로 마운트됨, 별도 생성 불필요)
- `/volume1/docker/lumisshow` — DB, 썸네일 캐시, 배경음악 저장 (컨테이너 재시작 후에도 유지)

---

## 2. 이미지 빌드

### 방법 A: SSH에서 직접 빌드 (권장)

```bash
# 소스 클론
cd /volume1/docker
git clone https://github.com/euikuk-jeong/lumisshow.git
cd lumisshow

# 이미지 빌드
docker build -f docker/Dockerfile -t lumisshow:latest .
```

### 방법 B: 로컬 PC에서 빌드 후 이미지 전송

```bash
# 로컬 PC에서
docker build -f docker/Dockerfile -t lumisshow:latest .
docker save lumisshow:latest | gzip > lumisshow.tar.gz

# NAS로 전송 후 SSH에서
docker load < lumisshow.tar.gz
```

---

## 3. 환경변수 파일 작성

```bash
# SSH에서
cp /volume1/docker/lumisshow/.env.example /volume1/docker/lumisshow/.env
vi /volume1/docker/lumisshow/.env
```

```dotenv
# .env — 실제 운영 값으로 반드시 변경
ADMIN_PASSWORD=여기에_강한_패스워드_입력
JWT_SECRET=여기에_랜덤_시크릿_입력
PHOTO_ROOT=/mnt/photos
DATA_DIR=/data
BASE_URL=http://192.168.1.100:8080   # NAS IP 또는 DDNS 주소
APP_PORT=8080
```

`JWT_SECRET`은 충분히 긴 랜덤 값을 사용합니다:

```bash
openssl rand -hex 32
```

---

## 4. docker-compose.yml

`/volume1/docker/lumisshow/docker/docker-compose.yml`을 아래 내용으로 사용합니다. 사진 폴더 경로(`/volume1/photo`)는 실제 NAS 구성에 맞게 수정하세요.

```yaml
services:
  lumisshow:
    image: lumisshow:latest
    container_name: lumisshow
    restart: unless-stopped
    ports:
      - "${APP_PORT:-8080}:${APP_PORT:-8080}"
    volumes:
      - /volume1/photo:/mnt/photos:ro       # NAS 사진 폴더 (읽기 전용)
      - /volume1/docker/lumisshow:/data     # DB, 썸네일, 음악 저장
    environment:
      - ADMIN_PASSWORD=${ADMIN_PASSWORD:?ADMIN_PASSWORD is required}
      - JWT_SECRET=${JWT_SECRET:?JWT_SECRET is required}
      - PHOTO_ROOT=/mnt/photos
      - DATA_DIR=/data
      - BASE_URL=${BASE_URL:-http://localhost:8080}
      - APP_PORT=${APP_PORT:-8080}
```

> **주의:** `PHOTO_ROOT` 볼륨은 반드시 `:ro`(읽기 전용)로 마운트해야 합니다. 원본 사진을 절대 수정하지 않습니다.

---

## 5. 컨테이너 실행

### SSH에서 실행

```bash
cd /volume1/docker/lumisshow
docker compose -f docker/docker-compose.yml --env-file .env up -d

# 로그 확인
docker logs -f lumisshow
```

### Container Manager GUI에서 실행

1. Container Manager → **프로젝트** → **만들기**
2. 프로젝트 이름: `lumisshow`
3. 경로: `/volume1/docker/lumisshow`
4. `docker-compose.yml` 파일 경로: `docker/docker-compose.yml`
5. 환경변수 파일(`.env`) 연결 후 배포

---

## 6. 환경변수 설명

| 변수 | 필수 | 설명 | 예시 |
|------|------|------|------|
| `ADMIN_PASSWORD` | ✓ | Admin 로그인 패스워드 | `MyStr0ngPass!` |
| `JWT_SECRET` | ✓ | JWT 서명 키 (32바이트 이상 권장) | `openssl rand -hex 32` 출력값 |
| `PHOTO_ROOT` | ✓ | 사진 폴더 마운트 경로 (컨테이너 내부) | `/mnt/photos` |
| `DATA_DIR` | ✓ | DB·썸네일·음악 저장 경로 (컨테이너 내부) | `/data` |
| `BASE_URL` |  | 공유 링크 URL 생성용 베이스 주소 | `https://lumis.mynas.synology.me` |
| `APP_PORT` |  | 서버 포트 (기본 `8080`) | `8080` |

---

## 7. HTTPS 설정 (Reverse Proxy)

DSM 내장 리버스 프록시를 통해 HTTPS를 적용합니다.

1. **DSM 제어판** → **로그인 포털** → **고급** 탭 → **리버스 프록시** → **만들기**
2. 설정:
   - **설명:** `lumisshow`
   - **소스 프로토콜:** `HTTPS`, 포트: `443` (또는 원하는 외부 포트)
   - **호스트명:** 사용할 도메인 또는 DDNS 주소
   - **대상 프로토콜:** `HTTP`
   - **대상 호스트명:** `localhost`
   - **대상 포트:** `8080`
3. `.env`의 `BASE_URL`을 `https://your-domain.com`으로 업데이트 후 컨테이너 재시작

> Synology DDNS 사용 시: DSM **제어판** → **외부 액세스** → **DDNS**에서 `*.synology.me` 무료 주소를 발급받을 수 있습니다.

---

## 8. 첫 실행 확인

브라우저에서 `http://NAS_IP:8080` 접속 후:

1. `/admin`으로 이동 → `ADMIN_PASSWORD`로 로그인
2. **사진 탐색**에서 NAS 사진 폴더가 정상 표시되는지 확인
3. 앨범 생성 → 공유 링크 생성 → 링크 접속 테스트

---

## 9. 업데이트

```bash
cd /volume1/docker/lumisshow

# 소스 업데이트
git pull

# 이미지 재빌드
docker build -f docker/Dockerfile -t lumisshow:latest .

# 컨테이너 재시작
docker compose -f docker/docker-compose.yml --env-file .env up -d
```

DB와 썸네일은 `/volume1/docker/lumisshow` 볼륨에 보존되므로 업데이트 후에도 데이터가 유지됩니다.

---

## 10. 트러블슈팅

### 컨테이너가 시작되지 않음
```bash
docker logs lumisshow
```
- `ADMIN_PASSWORD is required` 오류: `.env` 파일에서 `ADMIN_PASSWORD` 확인
- `JWT_SECRET is required` 오류: `.env` 파일에서 `JWT_SECRET` 확인

### 사진이 보이지 않음
- 볼륨 마운트 경로가 올바른지 확인: `/volume1/photo`가 실제로 존재하는지 확인
- `PHOTO_ROOT` 환경변수가 컨테이너 내부 마운트 경로(`/mnt/photos`)와 일치하는지 확인

### 썸네일이 생성되지 않음
- `/volume1/docker/lumisshow` 폴더에 쓰기 권한이 있는지 확인
- `docker logs lumisshow`에서 Pillow 관련 오류 확인

### 공유 링크 URL이 잘못됨
- `.env`의 `BASE_URL`을 실제 접속 주소로 설정 (`http://192.168.1.100:8080` 또는 `https://your-domain.com`)
- 변경 후 `docker compose ... up -d`로 재시작 필요
