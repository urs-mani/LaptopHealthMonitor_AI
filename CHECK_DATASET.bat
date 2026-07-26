@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run RUN_LAPTOP_HEALTH_MONITOR.bat once before checking the dataset.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m ai.verify_dataset
pause
