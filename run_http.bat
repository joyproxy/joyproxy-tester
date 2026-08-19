@echo off
rem Local HTTP mode (same UI as Android) for testing in browser.
cd /d "%~dp0"
".venv\Scripts\pip.exe" install flask -q
".venv\Scripts\python.exe" flask_server.py
