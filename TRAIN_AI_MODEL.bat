@echo off
setlocal
cd /d "%~dp0"
title Train Laptop Health Monitor AI Model
if not exist ".venv\Scripts\python.exe" (
  echo The application environment does not exist yet.
  echo Run RUN_LAPTOP_HEALTH_MONITOR.bat once, then run this file again.
  pause
  exit /b 1
)
echo ==========================================================
echo       NASA BATTERY RUL MODEL TRAINING
echo ==========================================================
echo.
".venv\Scripts\python.exe" -m ai.verify_dataset
if errorlevel 1 goto :error
echo.
echo Training and evaluating models. This can take several minutes...
".venv\Scripts\python.exe" -m ai.train_models
if errorlevel 1 goto :error
echo.
echo Training completed successfully.
echo Models: ai\models
echo Metrics and predictions: ai\reports
echo Restart the application to load the trained model.
pause
exit /b 0
:error
echo.
echo Training failed. Read the error above and DATASET_SETUP_GUIDE.txt.
pause
exit /b 1
