@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === LWB backend: cai dat lan dau tren Windows ===
set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Chua co Python. Cai Python 3.12+ tu python.org, tick "Add python.exe to PATH", roi chay lai.
  pause
  exit /b 1
)
if not exist ".venv-win\Scripts\python.exe" %PY% -m venv .venv-win
".venv-win\Scripts\python.exe" -m pip install --upgrade pip
".venv-win\Scripts\python.exe" -m pip install -r requirements-windows.txt
if not exist ".env" copy ".env.example" ".env"
".venv-win\Scripts\python.exe" manage.py migrate
echo.
echo Tao tai khoan dang nhap /admin (bo qua: nhan Ctrl+C):
".venv-win\Scripts\python.exe" manage.py createsuperuser
echo Xong. Tu gio chi can bam dup run_windows.bat
pause
