@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   MuJoCo Manipulator Control Lab
echo   메뉴에서 번호를 골라 4개 시뮬레이터를 체험하세요.
echo   (첫 실행은 준비 과정 때문에 몇 분 걸릴 수 있습니다.)
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" goto setup
if not exist "third_party\mujoco_menagerie\franka_emika_panda\scene.xml" goto setup
goto run

:setup
echo [준비 중] 처음이라 필요한 것들을 자동으로 설치합니다...
python "scripts\bootstrap_and_run.py" --setup-only
if errorlevel 1 (
  echo.
  echo [오류] 준비에 실패했습니다. 위 메시지를 확인하세요.
  echo Python 3.10 이상이 설치되어 있는지 먼저 확인해 주세요.
  pause
  exit /b %errorlevel%
)

:run
".venv\Scripts\python.exe" -m mclab menu
echo.
echo 메뉴를 닫았습니다. 이 창은 이제 닫아도 됩니다.
pause
