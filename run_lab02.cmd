@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto setup
goto run

:setup
python "scripts\bootstrap_and_run.py" --setup-only

:run
".venv\Scripts\python.exe" -m mclab run lab02 --config configs\lab02_pid\default.yaml --viewer --hide-viewer-ui --realtime --pause-at-end --plot --plots essential
