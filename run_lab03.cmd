@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto setup
goto run

:setup
python "scripts\bootstrap_and_run.py" --setup-only

:run
".venv\Scripts\python.exe" -m mclab run lab03 --config configs\lab03_2dof\joint_space_2dof.yaml --viewer --realtime --pause-at-end --plot --plots essential
