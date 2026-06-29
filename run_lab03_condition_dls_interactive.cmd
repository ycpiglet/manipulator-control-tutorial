@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto setup
goto run

:setup
python "scripts\bootstrap_and_run.py" --setup-only
if errorlevel 1 exit /b %errorlevel%

:run
".venv\Scripts\python.exe" -m mclab run lab03 --config configs\lab03_2dof\condition_aware_dls_2dof.yaml --viewer --realtime --pause-at-end --plot --plots dls --open-report
