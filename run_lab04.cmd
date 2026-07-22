@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto setup
if not exist "third_party\mujoco_menagerie\franka_emika_panda\scene.xml" goto setup
".venv\Scripts\python.exe" "scripts\install_locked.py" --check runtime >nul 2>&1
if errorlevel 1 goto setup
goto run

:setup
python "scripts\bootstrap_and_run.py" --setup-only
if errorlevel 1 exit /b %errorlevel%

:run
".venv\Scripts\python.exe" -m mclab run lab04 --config configs\lab04_panda\joint_pd.yaml --viewer --realtime --pause-at-end --plot --plots essential --open-report
