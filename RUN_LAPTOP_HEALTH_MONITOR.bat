@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Laptop Health Monitor

 echo ==========================================================
 echo              LAPTOP HEALTH MONITOR
 echo ==========================================================
 echo.

rem Select a supported Python explicitly. "py -3" can choose Python 3.14,
rem for which some project dependencies may not yet provide Windows wheels.
set "PY_CMD="
where py >nul 2>nul
if not errorlevel 1 (
    py -3.12 -c "import sys" >nul 2>nul && set "PY_CMD=py -3.12"
    if not defined PY_CMD py -3.11 -c "import sys" >nul 2>nul && set "PY_CMD=py -3.11"
    if not defined PY_CMD py -3.13 -c "import sys" >nul 2>nul && set "PY_CMD=py -3.13"
)

if not defined PY_CMD (
    where python >nul 2>nul
    if not errorlevel 1 (
        for /f "delims=" %%V in ('python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') do set "PY_VER=%%V"
        if "!PY_VER!"=="3.11" set "PY_CMD=python"
        if "!PY_VER!"=="3.12" set "PY_CMD=python"
        if "!PY_VER!"=="3.13" set "PY_CMD=python"
    )
)

if not defined PY_CMD (
    echo A supported Python version was not found.
    echo.
    echo Install 64-bit Python 3.11, 3.12, or 3.13 from python.org.
    echo During setup, enable "Add python.exe to PATH" and "Install launcher".
    echo Python 3.14 is intentionally not used because some required Windows
    echo packages may not yet have compatible pre-built wheels.
    echo.
    pause
    exit /b 1
)

for /f "delims=" %%V in ('%PY_CMD% -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set "SELECTED_VER=%%V"
echo Using Python !SELECTED_VER!.

rem Recreate an environment made by another Python version or old dependency set.
set "ENV_REBUILD=0"
if exist ".venv\Scripts\python.exe" (
    for /f "delims=" %%V in ('".venv\Scripts\python.exe" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') do set "VENV_VER=%%V"
    if not "!VENV_VER!"=="!SELECTED_VER!" set "ENV_REBUILD=1"
    if not exist ".venv\.lhm_dependencies_ai_v1" set "ENV_REBUILD=1"
)

if "!ENV_REBUILD!"=="1" (
    echo Removing the incompatible or outdated environment...
    rmdir /s /q ".venv"
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating isolated Python environment...
    %PY_CMD% -m venv .venv
    if errorlevel 1 goto :error
) else (
    echo [1/3] Existing isolated environment is compatible.
)

set "VENV_PY=.venv\Scripts\python.exe"

echo [2/3] Checking required packages...
"%VENV_PY%" -c "import PyQt6, pyqtgraph, numpy, pandas, psutil, sklearn, joblib, matplotlib, reportlab, openpyxl" >nul 2>nul
if errorlevel 1 (
    echo Installing pre-built dependency packages. This is needed only once...
    "%VENV_PY%" -m pip install --disable-pip-version-check --only-binary=:all: -r requirements.txt
    if errorlevel 1 goto :install_error
)

rem Mark this exact dependency generation as installed.
type nul > ".venv\.lhm_dependencies_ai_v1"

echo [3/3] Validating and starting application...
"%VENV_PY%" -m compileall -q main.py controllers monitors models reports database utils ai verify_project.py
if errorlevel 1 goto :error
"%VENV_PY%" main.py
if errorlevel 1 goto :error
exit /b 0

:install_error
echo.
echo Dependency installation failed.
echo Confirm that the computer has internet access and uses 64-bit Python
 echo 3.11, 3.12, or 3.13. Then run this file again.
echo.
pause
exit /b 1

:error
echo.
echo The application could not start. Review the message above.
echo Diagnostic command: .venv\Scripts\python.exe main.py
echo.
pause
exit /b 1
