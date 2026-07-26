@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run RUN_LAPTOP_HEALTH_MONITOR.bat once to create the environment.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" verify_project.py
pause
