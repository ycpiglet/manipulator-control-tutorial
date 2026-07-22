@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto setup
".venv\Scripts\python.exe" "scripts\install_locked.py" --check runtime >nul 2>&1
if errorlevel 1 goto setup
goto run

:setup
python "scripts\bootstrap_and_run.py" --setup-only
if errorlevel 1 exit /b %errorlevel%

:run
".venv\Scripts\python.exe" -m mclab run lab01 --config configs\lab01_msd\default.yaml --viewer --realtime --pause-at-end --plot --plots essential --open-report
