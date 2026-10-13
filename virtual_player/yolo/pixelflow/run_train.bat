@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat

echo === 1) Re-build dataset from current labels ===
python labels_levels_to_yolo.py %*

echo.
echo === 2) Train YOLO ===
python train_levels.py

pause
