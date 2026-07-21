@echo off
setlocal
cd /d "%~dp0"

echo Starting MCLab. The first setup can take a few minutes.
python "scripts\start_mclab.py" %*
if errorlevel 1 (
  echo.
  echo MCLab could not start. Run: python -m mclab doctor
  pause
  exit /b %errorlevel%
)
