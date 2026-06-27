@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto setup
goto run

:setup
python "scripts\bootstrap_and_run.py" --setup-only

:run
".venv\Scripts\python.exe" -m mclab batch lab03_2dof_compare --open-report
