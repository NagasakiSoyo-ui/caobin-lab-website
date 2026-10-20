@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>nul
  if errorlevel 1 (
    python -m venv .venv
  ) else (
    py -3 -m venv .venv
  )
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" setup_local.py
if errorlevel 1 goto failed
echo Website: http://127.0.0.1:8771/
echo Admin:   http://127.0.0.1:8771/manage/
echo Keep this window open while using the website.
start "" "http://127.0.0.1:8771/manage/"
".venv\Scripts\waitress-serve.exe" --listen=127.0.0.1:8771 --max-request-body-size=60000000 config.wsgi:application
if errorlevel 1 goto failed
exit /b 0
:failed
echo Startup failed. Read the error above. Python 3.10+ and dependencies are required.
pause
exit /b 1
