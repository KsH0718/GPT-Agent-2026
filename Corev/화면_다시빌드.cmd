@echo off
setlocal
cd /d "%~dp0"
start "" "..\venv\Scripts\pythonw.exe" "%~dp0launcher.py" --rebuild
