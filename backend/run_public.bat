@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv-win\Scripts\python.exe" (
  echo Chua cai dat. Chay setup_windows.bat truoc.
  pause
  exit /b 1
)
rem === Che do public (chia se dashboard qua Tailscale Funnel) ===
rem DJANGO_SECRET_KEY phai la gia tri that trong .env, neu khong Django se bao loi va dung.
set "LWB_PUBLIC=1"
set "DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,.ts.net"
rem CSRF origin: lay ten may Tailscale (xxx.ts.net). Dat san LWB_PUBLIC_ORIGINS de bo qua buoc nay.
if not defined LWB_PUBLIC_ORIGINS for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "try { (tailscale status --json | ConvertFrom-Json).Self.DNSName.TrimEnd('.') } catch {}" 2^>nul`) do set "LWB_PUBLIC_ORIGINS=https://%%i"
".venv-win\Scripts\python.exe" manage.py migrate --noinput
if errorlevel 1 (
  echo.
  echo Khoi dong that bai ^(xem loi o tren^). Che do public can DJANGO_SECRET_KEY that trong .env.
  pause
  exit /b 1
)
start "LWB mqtt consumer (public)" cmd /k ""%~dp0.venv-win\Scripts\python.exe" "%~dp0manage.py" mqtt_consumer"
start "LWB web (public)" cmd /k ""%~dp0.venv-win\Scripts\python.exe" "%~dp0manage.py" runserver 127.0.0.1:8000"
echo.
echo ===== CHE DO PUBLIC =====
echo Web dang chay tai http://127.0.0.1:8000 ^(/admin/ da tat, DEBUG tat^).
if defined LWB_PUBLIC_ORIGINS (echo Link public se la: %LWB_PUBLIC_ORIGINS%) else (echo Khong lay duoc ten may Tailscale; link se co dang https://TEN-MAY.ts.net)
echo.
echo Script nay KHONG tu bat Funnel. De chia se, mo mot cua so khac va chay:
echo     tailscale funnel --bg 127.0.0.1:8000
echo Xem link/trang thai:   tailscale funnel status
echo TAT Funnel khi xong:   tailscale funnel reset
echo.
echo Luu y: ai co link deu xem duoc du lieu. KHONG public cong 8001 ^(Mobile API^).
echo Funnel phai duoc bat truoc trong trang quan tri Tailscale ^(xem README_WINDOWS.md^).
echo Dong 2 cua so "LWB ... (public)" de dung web; nho chay "tailscale funnel reset".
