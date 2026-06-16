#!/usr/bin/env bash
cd "$(dirname "$0")"

export ADMIN_PASSWORD=dev_password
export JWT_SECRET=dev_secret_key
export PHOTO_ROOT=./testdata/photos
export DATA_DIR=./testdata/data
export BASE_URL=http://localhost:8080

# APP_VERSION from git tag
export APP_VERSION=$(git describe --tags --abbrev=0 2>/dev/null || echo "dev")

# LAN IP for mobile testing
LAN_IP=$(ipconfig 2>/dev/null \
  | grep -i "IPv4" \
  | grep -v "169.254" \
  | head -1 \
  | awk -F': ' '{print $2}' \
  | tr -d ' \r')

echo
echo " [LumisShow Local Test]"
echo " Version: $APP_VERSION"
echo " PC:      http://localhost:8080"
[ -n "$LAN_IP" ] && echo " Mobile:  http://$LAN_IP:8080  (same Wi-Fi)"
echo " Quit:    Ctrl+C"
echo

.venv/Scripts/uvicorn backend.main:app --reload --host 0.0.0.0 --port 8080
