@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto setup
".venv\Scripts\python.exe" "scripts\install_locked.py" --check runtime >nul 2>&1
if errorlevel 1 goto setup
".venv\Scripts\python.exe" -m mclab assets verify >nul 2>&1
if errorlevel 1 goto setup
goto run

:setup
python "scripts\bootstrap_and_run.py" --setup-only
if errorlevel 1 exit /b %errorlevel%

:run
".venv\Scripts\python.exe" -m mclab batch lab04_cartesian_compare --open-report
