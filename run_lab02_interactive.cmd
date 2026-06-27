@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto setup
goto run

:setup
python "scripts\bootstrap_and_run.py" --setup-only
if errorlevel 1 exit /b %errorlevel%

:run
".venv\Scripts\python.exe" -m mclab run lab02 --config configs\lab02_pid\interactive_disturbance.yaml --viewer --realtime --pause-at-end --plot --plots essential --open-report
