@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto setup
goto run

:setup
python "scripts\bootstrap_and_run.py" --setup-only

:run
".venv\Scripts\python.exe" -m mclab run lab03 --config configs\lab03_2dof\minimum_jerk.yaml --viewer --hide-viewer-ui --realtime --pause-at-end --plot --plots essential
