#!/bin/bash
# LumisShow nas-dev 검증 서버 — 소스를 직접 실행(이미지 빌드 없음, --reload)
#
# 사용:
#   scripts/dev-server.sh test              샘플 사진 + 빈 DB
#   scripts/dev-server.sh prod              운영 사진(ro) + 운영 data 스냅샷 복사본
#   scripts/dev-server.sh prod --refresh    스냅샷을 운영에서 새로 복사한 뒤 실행
#   scripts/dev-server.sh test --refresh    dev data를 비우고(빈 DB) 실행
#   옵션: --port N (기본 8090)
#
# 환경변수(필요 시 덮어쓰기):
#   DEV_ROOT     dev data 루트            (기본 ~/lumisshow-dev)
#   PROD_DATA    운영 data 폴더 mount(ro) (기본 /mnt/prod-data)
#   PROD_PHOTOS  운영 사진 폴더 mount(ro) (기본 /mnt/photos)
#   DEV_PORT, DEV_BASE_URL, DEV_ADMIN_PASSWORD
#
# 운영 data는 읽기만 한다. 앱은 $DEV_ROOT/<모드>/data 의 복사본만 읽고 쓴다.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="$REPO/.venv/bin/python"
DEV_ROOT="${DEV_ROOT:-$HOME/lumisshow-dev}"
PROD_DATA="${PROD_DATA:-/mnt/prod-data}"
PROD_PHOTOS="${PROD_PHOTOS:-/mnt/photos}"
PORT="${DEV_PORT:-8090}"

usage() { sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-1}"; }
die() { echo "오류: $*" >&2; exit 1; }

MODE="${1:-}"; [ -n "$MODE" ] || usage
shift || true
REFRESH=0
while [ $# -gt 0 ]; do
  case "$1" in
    --refresh) REFRESH=1 ;;
    --port) [ $# -ge 2 ] || die "--port 값이 없음"; PORT="$2"; shift ;;
    -h|--help) usage 0 ;;
    *) die "알 수 없는 옵션: $1" ;;
  esac
  shift
done
case "$MODE" in test|prod) ;; -h|--help) usage 0 ;; *) usage ;; esac
case "$PORT" in ''|*[!0-9]*) die "포트는 숫자여야 함: $PORT" ;; esac

[ -x "$PY" ] || die "$PY 없음 — .venv를 먼저 만들 것"
[ -n "$DEV_ROOT" ] && [ "$DEV_ROOT" != "/" ] || die "DEV_ROOT가 비정상: '$DEV_ROOT'"

DATA_DIR="$DEV_ROOT/$MODE/data"

# ── 안전장치: dev data가 운영 data와 겹치면 중단 ─────────────────────────────
real_dev="$(realpath -m "$DATA_DIR")"
real_prod="$(realpath -m "$PROD_DATA")"
case "$real_dev/" in "$real_prod"/*) die "dev data($real_dev)가 운영 data($real_prod) 안에 있음" ;; esac
case "$real_prod/" in "$real_dev"/*) die "운영 data($real_prod)가 dev data($real_dev) 안에 있음" ;; esac

safe_rm() {  # $DEV_ROOT 아래 경로만 삭제
  case "$(realpath -m "$1")/" in
    "$(realpath -m "$DEV_ROOT")"/?*) chmod -R u+rwX -- "$1" 2>/dev/null || true; rm -rf -- "$1" ;;
    *) die "DEV_ROOT 밖 경로는 삭제하지 않음: $1" ;;
  esac
}

snapshot_db() {  # $1=원본 $2=대상 — SQLite backup API로 일관된 스냅샷 (운영이 쓰는 중이어도 안전)
  "$PY" - "$1" "$2" <<'PYEOF'
import sqlite3, sys
from urllib.parse import quote
src, dst = sys.argv[1], sys.argv[2]
s = sqlite3.connect("file:" + quote(src) + "?mode=ro", uri=True, timeout=30)
d = sqlite3.connect(dst)
s.backup(d)
d.close()
s.close()
PYEOF
}

# ── 모드별 준비 ───────────────────────────────────────────────────────────────
if [ "$MODE" = "test" ]; then
  PHOTO_ROOT="$REPO/testdata/photos"
  if [ ! -d "$PHOTO_ROOT" ] || [ -z "$(ls -A "$PHOTO_ROOT" 2>/dev/null)" ]; then
    echo "샘플 사진 생성..."
    "$PY" "$REPO/scripts/make-test-photos.py" "$PHOTO_ROOT"
  fi
  [ "$REFRESH" = 1 ] && [ -d "$DATA_DIR" ] && { echo "dev data 초기화: $DATA_DIR"; safe_rm "$DATA_DIR"; }
  mkdir -p "$DATA_DIR"
else
  PHOTO_ROOT="$PROD_PHOTOS"
  [ -d "$PHOTO_ROOT" ] || die "운영 사진 폴더 없음: $PHOTO_ROOT — nas-dev 컨테이너에 mount 필요"
  if [ "$REFRESH" = 1 ] || [ ! -f "$DATA_DIR/db/app.db" ]; then
    [ -f "$PROD_DATA/db/app.db" ] || die "운영 DB 없음: $PROD_DATA/db/app.db — mount 경로 확인"
    echo "운영 data 스냅샷 복사: $PROD_DATA → $DATA_DIR"
    [ -d "$DATA_DIR" ] && safe_rm "$DATA_DIR"
    mkdir -p "$DATA_DIR/db"
    snapshot_db "$PROD_DATA/db/app.db" "$DATA_DIR/db/app.db"
    if [ -f "$PROD_DATA/db/ai.db" ]; then
      snapshot_db "$PROD_DATA/db/ai.db" "$DATA_DIR/db/ai.db"
    fi
    # 음악·얼굴 크롭은 파일 복사. 썸네일은 용량이 커서 복사하지 않고 dev에서 다시 생성
    for sub in music faces; do
      [ -d "$PROD_DATA/$sub" ] && cp -a "$PROD_DATA/$sub" "$DATA_DIR/$sub"
    done
    chmod -R u+rwX "$DATA_DIR"  # 원본 권한(읽기 전용 등)이 복사돼도 dev에서는 쓸 수 있어야 함
    echo "  완료 ($(du -sh "$DATA_DIR" | cut -f1))"
  fi
fi

# ── 인증 값: dev 전용, 한 번 만들어 재사용 ────────────────────────────────────
SECRETS="$DEV_ROOT/secrets.env"
if [ ! -f "$SECRETS" ]; then
  mkdir -p "$DEV_ROOT"
  umask 077
  "$PY" - > "$SECRETS" <<'PYEOF'
import secrets
print("DEV_JWT_SECRET=" + secrets.token_hex(32))
print("DEV_ADMIN_PASSWORD_GEN=" + secrets.token_urlsafe(9))
PYEOF
fi
DEV_JWT_SECRET="$(sed -n 's/^DEV_JWT_SECRET=//p' "$SECRETS")"
ADMIN_PW="${DEV_ADMIN_PASSWORD:-$(sed -n 's/^DEV_ADMIN_PASSWORD_GEN=//p' "$SECRETS")}"

# ── 실행 ──────────────────────────────────────────────────────────────────────
cd "$REPO"
VERSION="dev-$(git describe --tags --always --dirty 2>/dev/null || echo unknown)"
BRANCH="$(git branch --show-current 2>/dev/null || true)"

unset ADMIN_PASSWORD_HASH
export ADMIN_PASSWORD="$ADMIN_PW"
export JWT_SECRET="$DEV_JWT_SECRET"
export PHOTO_ROOT DATA_DIR
export BASE_URL="${DEV_BASE_URL:-http://localhost:$PORT}"
export APP_VERSION="$VERSION"

cat <<EOF
==============================
 LumisShow dev 서버 ($MODE)
==============================
 브랜치   : ${BRANCH:-?}
 버전     : $VERSION
 사진     : $PHOTO_ROOT
 data     : $DATA_DIR
 주소     : $BASE_URL  (0.0.0.0:$PORT)
 Admin PW : $ADMIN_PW
==============================
EOF

exec "$PY" -m uvicorn backend.main:app --host 0.0.0.0 --port "$PORT" --reload --reload-dir backend
