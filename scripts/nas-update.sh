#!/bin/bash
# LumisShow NAS 배포 스크립트
#
# [최초 설정] NAS에 이 파일을 복사하고 실행 권한 부여:
#   scp scripts/nas-update.sh user@nas-ip:/volume1/docker/project/upload/lumisshow/update.sh
#   ssh user@nas-ip 'chmod +x /volume1/docker/project/upload/lumisshow/update.sh'
#
# [이후 업데이트 실행]:
#   ssh user@nas-ip '/volume1/docker/project/upload/lumisshow/update.sh'
#
# ──────────────────────────────────────────────
# [다른 프로젝트에 재사용할 때 수정할 항목]
#
#   1. IMAGE
#      GHCR에 등록된 본인 이미지명으로 변경
#      예) "ghcr.io/your-username/your-project"
#
#   2. COMPOSE_FILE
#      NAS에서 docker-compose.yml 파일의 실제 절대경로로 변경
#      예) "/volume1/docker/your-project/docker-compose.yml"
#
#   3. CONTAINER_NAME
#      docker-compose.yml 의 container_name 값과 동일하게 변경
#      (컨테이너 강제 중지 fallback에 사용됨)
#      예) "your-project"
# ──────────────────────────────────────────────

set -euo pipefail

IMAGE="ghcr.io/euikuk-jeong/lumisshow"
AI_IMAGE="ghcr.io/euikuk-jeong/lumisshow-ai"
COMPOSE_FILE="/volume1/docker/project/upload/lumisshow/docker-compose.yml"
CONTAINER_NAME="lumisshow"

echo "=============================="
echo " LumisShow 배포 시작"
echo "=============================="

# 1. 최신 이미지 pull
echo ""
echo "[1/4] 최신 이미지 pull..."
docker compose -f "$COMPOSE_FILE" pull

# 2. 컨테이너 중지
echo ""
echo "[2/4] 컨테이너 중지..."
docker compose -f "$COMPOSE_FILE" down 2>/dev/null \
  || { echo "  compose down 실패 → docker stop으로 강제 중지"; docker stop "$CONTAINER_NAME" 2>/dev/null || true; docker rm "$CONTAINER_NAME" 2>/dev/null || true; }

# 3. 컨테이너 시작
echo ""
echo "[3/4] 컨테이너 시작..."
docker compose -f "$COMPOSE_FILE" up -d

# 4. 구버전 이미지 삭제
echo ""
echo "[4/4] 구버전 이미지 정리..."

# :latest 외 버전 태그 이미지 삭제 (ghcr.io 에서 pull된 0.x.x 태그 등, 워커 이미지 포함)
OLD_IMAGES=$(docker images "$IMAGE" --format "{{.Tag}}\t{{.ID}}" | grep -v "^latest" | awk '{print $2}'; docker images "$AI_IMAGE" --format "{{.Tag}}\t{{.ID}}" | grep -v "^latest" | awk '{print $2}')
if [ -n "$OLD_IMAGES" ]; then
  echo "$OLD_IMAGES" | xargs docker rmi -f 2>/dev/null && echo "  버전 태그 이미지 삭제 완료" || echo "  일부 이미지 삭제 실패 (사용 중일 수 있음, 무시)"
else
  echo "  삭제할 버전 태그 이미지 없음"
fi

# dangling 이미지 삭제 (이전 :latest)
docker image prune -f

echo ""
echo "=============================="
echo " 배포 완료"
echo "=============================="
echo ""
docker compose -f "$COMPOSE_FILE" ps
