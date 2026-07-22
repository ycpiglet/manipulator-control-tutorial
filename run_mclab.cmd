@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto setup
".venv\Scripts\python.exe" "scripts\install_locked.py" --check app >nul 2>&1
if errorlevel 1 goto setup
".venv\Scripts\python.exe" -c "import mclab, PySide6" >nul 2>&1
if errorlevel 1 goto setup
".venv\Scripts\python.exe" -m mclab assets verify >nul 2>&1
if errorlevel 1 goto setup
goto run

:setup
python "scripts\start_mclab.py" --setup-only
if errorlevel 1 exit /b %errorlevel%

:run
".venv\Scripts\python.exe" -m mclab menu
exit /b %errorlevel%
