@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   MuJoCo Manipulator Control Lab
echo   Pick a number in the menu to try the four simulators.
echo   (The first run may take a few minutes to set up.)
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" goto setup
if not exist "third_party\mujoco_menagerie\franka_emika_panda\scene.xml" goto setup
goto run

:setup
echo [Setup] First run: installing what the labs need...
python "scripts\bootstrap_and_run.py" --setup-only
if errorlevel 1 (
  echo.
  echo [Error] Setup failed. Please check the message above.
  echo Make sure Python 3.10 or newer is installed first.
  pause
  exit /b %errorlevel%
)

:run
".venv\Scripts\python.exe" -m mclab menu
echo.
echo Menu closed. You can close this window now.
pause
