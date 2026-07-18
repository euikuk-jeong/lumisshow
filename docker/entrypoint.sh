#!/bin/sh
# PUID/PGID 미설정 시 기존 동작(root) 그대로 유지 — 하위 호환 기본값
set -e

if [ -n "$PUID" ] && [ -n "$PGID" ]; then
  if [ -z "$DATA_DIR" ]; then
    echo "entrypoint: PUID/PGID 설정 시 DATA_DIR 환경변수도 필요합니다" >&2
    exit 1
  fi

  current_owner=$(stat -c '%u:%g' "$DATA_DIR")
  target_owner="$PUID:$PGID"
  if [ "$current_owner" != "$target_owner" ]; then
    echo "entrypoint: $DATA_DIR 소유권을 $target_owner 로 변경 중 (최초 1회, 파일 많으면 시간 걸릴 수 있음)"
    chown -R "$PUID:$PGID" "$DATA_DIR"
  fi

  if ! getent passwd "$PUID" >/dev/null 2>&1; then
    echo "appuser:x:$PUID:$PGID::/tmp:/usr/sbin/nologin" >> /etc/passwd
  fi

  export HOME=/tmp
  exec setpriv --reuid "$PUID" --regid "$PGID" --clear-groups "$@"
fi

exec "$@"
