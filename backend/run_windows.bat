@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv-win\Scripts\python.exe" (
  echo Chua cai dat. Chay setup_windows.bat truoc.
  pause
  exit /b 1
)
".venv-win\Scripts\python.exe" manage.py migrate --noinput
set "TSIP="
for /f "usebackq delims=" %%i in (`tailscale ip -4 2^>nul`) do set "TSIP=%%i"
echo %TSIP%| findstr /r "^[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*$" >nul
if errorlevel 1 set "TSIP="
if not defined TSIP echo Khong lay duoc IP Tailscale ^(chua cai/chua dang nhap Tailscale^). Bo qua cua so web Tailscale.
start "LWB mqtt consumer" cmd /k ""%~dp0.venv-win\Scripts\python.exe" "%~dp0manage.py" mqtt_consumer"
start "LWB web server" cmd /k ""%~dp0.venv-win\Scripts\python.exe" "%~dp0manage.py" runserver 127.0.0.1:8000"
if defined TSIP start "LWB web (Tailscale)" cmd /k "set DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,%TSIP%&& "%~dp0.venv-win\Scripts\python.exe" "%~dp0manage.py" runserver %TSIP%:8000"
start "LWB mobile api" cmd /k "set LWB_MOBILE_ALLOWED_HOSTS=*&& "%~dp0.venv-win\Scripts\python.exe" "%~dp0manage.py" runserver 0.0.0.0:8001 --settings=config.lwb_mobile_local"
timeout /t 4 >nul
start "" http://127.0.0.1:8000/
echo Dashboard: http://127.0.0.1:8000/   Admin: http://127.0.0.1:8000/admin/
echo Mobile API (app Android, qua Tailscale): http://IP-TAILSCALE:8001/api/mobile/v1/
if defined TSIP echo Dashboard tren dien thoai: http://%TSIP%:8000
if defined TSIP echo App Flutter (Android): http://%TSIP%:8001
echo Dong cac cua so "LWB ..." (consumer, web, web Tailscale, mobile api) de dung he thong.
