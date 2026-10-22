@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
"runtime\python.exe" -B "launcher.py"
if errorlevel 1 pause
