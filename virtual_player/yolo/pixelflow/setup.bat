@echo off
REM PixelFlow Setup - 진단용 강화 버전
REM 어떤 단계에서 멈추든 창이 닫히지 않음

setlocal EnableDelayedExpansion
chcp 65001 >NUL 2>&1
title PixelFlow Setup

cd /d "%~dp0"

echo.
echo ====================================================
echo   PixelFlow Setup
echo   Folder: %CD%
echo ====================================================
echo.

REM ========== 1) Python check ==========
echo [1/5] Checking Python...
python --version
if errorlevel 1 (
    echo.
    echo ============================================================
    echo  ERROR: Python is NOT installed or not in PATH
    echo ============================================================
    echo.
    echo Please install Python 3.11+ from:
    echo   https://www.python.org/downloads/
    echo.
    echo IMPORTANT: During install, CHECK the box:
    echo   [v] Add python.exe to PATH
    echo.
    echo After install, RESTART this setup.bat
    echo.
    pause
    exit /b 1
)
echo OK
echo.

REM ========== 2) Pip check ==========
echo [2/5] Checking pip...
python -m pip --version
if errorlevel 1 (
    echo.
    echo ERROR: pip not available
    echo Try: python -m ensurepip --upgrade
    echo.
    pause
    exit /b 1
)
echo OK
echo.

REM ========== 3) Create venv ==========
echo [3/5] Creating virtual environment...
if exist venv (
    echo   venv already exists, skipping
) else (
    python -m venv venv
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to create venv
        echo Try: python -m pip install --user virtualenv
        echo.
        pause
        exit /b 1
    )
    echo   venv created
)
echo OK
echo.

REM ========== 4) Install dependencies ==========
echo [4/5] Installing dependencies (5~10 min)...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo.
    echo ERROR: Failed to activate venv
    echo Run: venv\Scripts\activate.bat manually
    echo.
    pause
    exit /b 1
)

python -m pip install --upgrade pip
if errorlevel 1 (
    echo WARNING: pip upgrade failed, continuing...
)

python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: Dependency install failed
    echo.
    echo Possible causes:
    echo   - Network issue
    echo   - Firewall blocking PyPI
    echo.
    echo Try manually:
    echo   venv\Scripts\activate
    echo   pip install ultralytics PySide6 opencv-python pillow numpy
    echo.
    pause
    exit /b 1
)
echo OK
echo.

REM ========== 5) CUDA check ==========
echo [5/5] Checking GPU/CUDA...
python -c "import torch; print('CUDA:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU only')"
echo.

echo ====================================================
echo   Setup COMPLETE
echo ====================================================
echo.
echo Next steps:
echo   run_gui.bat       - Open Label Editor
echo   run_train.bat     - Convert + Train YOLO
echo   run_evaluate.bat  - Evaluate trained model
echo.
pause
