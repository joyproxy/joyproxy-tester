@echo off
rem JoyProxy Test - one-time environment setup
cd /d "%~dp0"
echo [JoyProxy Test] Creating virtual environment...
py -m venv .venv 2>nul || python -m venv .venv
echo [JoyProxy Test] Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
echo.
echo [JoyProxy Test] Done. Double-click run.bat to start.
pause
