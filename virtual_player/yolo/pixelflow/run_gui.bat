@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
python label_editor.py %*
