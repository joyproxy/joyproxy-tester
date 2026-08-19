@echo off
rem JoyProxy Test - portable launcher (no console window)
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "app.py"
) else (
    echo [JoyProxy Test] Virtual environment not found.
    echo Run setup.bat first to create it, or use a bundled exe build.
    pause
)
