@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set "PY=C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe"
set "HERE=%~dp0"
set "OUT=%HERE%pixellab_auth.json"

echo ============================================
echo  PixelLab login session capture
echo ============================================
echo.

if not exist "%PY%" (
  echo [X] Python not found at %PY%
  echo     Adjust PY path inside this .bat file.
  pause
  exit /b 1
)
echo [1/4] Python OK: %PY%
echo.

echo [2/4] Installing Playwright (one-time, ~30s)...
"%PY%" -m pip install --quiet --disable-pip-version-check playwright
if errorlevel 1 (
  echo [X] pip install failed
  pause
  exit /b 1
)
echo       done.
echo.

echo [3/4] Installing Chromium (one-time, ~1-2min, 150MB)...
"%PY%" -m playwright install chromium
if errorlevel 1 (
  echo [X] chromium install failed
  pause
  exit /b 1
)
echo       done.
echo.

echo [4/4] Launching login capture...
echo       - Chromium window will open with PixelLab signin page
echo       - Click "Sign in with Google" and complete Google login
echo       - When you see PixelLab dashboard, RETURN to this window
echo       - Press ENTER here
echo.
"%PY%" "%HERE%pixellab_login_export.py"

echo.
if exist "%OUT%" (
  for %%A in ("%OUT%") do echo [OK] saved: %%~fA  ^(%%~zA bytes^)
  echo.
  echo NEXT - upload to Mother:
  echo     scp "%OUT%" aimed@100.77.190.68:~/.hermes/watcher/pixellab_auth.json
) else (
  echo [X] pixellab_auth.json was not created. Did the Chromium window close before ENTER?
)

echo.
pause
