@echo off
cd /d "%~dp0"

set ADMIN_PASSWORD=dev_password
set JWT_SECRET=dev_secret_key
set PHOTO_ROOT=./testdata/photos
set DATA_DIR=./testdata/data
set BASE_URL=http://localhost:8080

rem -- git tag에서 APP_VERSION 자동 설정
for /f %%i in ('git describe --tags --abbrev=0 2^>nul') do set APP_VERSION=%%i
if not defined APP_VERSION set APP_VERSION=dev

rem -- LAN IP 자동 감지 (단말 테스트용)
set LAN_IP=
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /i "IPv4" ^| findstr /v "169.254"') do (
  if not defined LAN_IP set LAN_IP=%%i
)
set LAN_IP=%LAN_IP: =%

echo.
echo  [LumisShow 로컬 테스트]
echo  PC:     http://localhost:8080
if defined LAN_IP (
  echo  단말:   http://%LAN_IP%:8080  (같은 Wi-Fi 필요)
)
echo  종료:   Ctrl+C
echo.

.venv\Scripts\uvicorn backend.main:app --reload --host 0.0.0.0 --port 8080
