@echo off
cd /d "%~dp0"

set ADMIN_PASSWORD=dev_password
set JWT_SECRET=dev_secret_key
set PHOTO_ROOT=./testdata/photos
set DATA_DIR=./testdata/data
set BASE_URL=http://localhost:8080

rem -- APP_VERSION from git tag
for /f %%i in ('git describe --tags --abbrev=0 2^>nul') do set APP_VERSION=%%i
if not defined APP_VERSION set APP_VERSION=dev

rem -- LAN IP for mobile testing
set LAN_IP=
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /i "IPv4" ^| findstr /v "169.254"') do (
  if not defined LAN_IP set LAN_IP=%%i
)
set LAN_IP=%LAN_IP: =%

echo.
echo  [LumisShow Local Test]
echo  PC:     http://localhost:8080
if defined LAN_IP (
  echo  Mobile: http://%LAN_IP%:8080  (same Wi-Fi)
)
echo  Quit:   Ctrl+C
echo.

.venv\Scripts\uvicorn backend.main:app --reload --host 0.0.0.0 --port 8080
