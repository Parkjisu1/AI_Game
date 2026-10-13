@echo off
REM ============================================================
REM  Multi-Genre Labeler — PyInstaller build (Windows)
REM  Output: dist\MultiGenreLabeler.exe
REM ============================================================
setlocal

REM Move to project root (one level up from build/)
pushd "%~dp0\.."

set PYTHON=C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe
if not exist "%PYTHON%" (
    set PYTHON=python
)

echo [1/3] Cleaning previous builds...
if exist build_cache rmdir /s /q build_cache
if exist dist rmdir /s /q dist

echo [2/3] Running PyInstaller...
"%PYTHON%" -m PyInstaller --clean --workpath build_cache --distpath dist build\label_tool.spec
if errorlevel 1 (
    echo Build FAILED.
    popd
    exit /b 1
)

echo [3/3] Done.
echo Output: %CD%\dist\MultiGenreLabeler.exe
echo.
dir dist /b
popd
endlocal
