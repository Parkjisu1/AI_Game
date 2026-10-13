@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
python predict_with_model.py %*
pause
