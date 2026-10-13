@echo off
echo === Drives ===
wmic logicaldisk where "drivetype=3" get caption,freespace
echo.
echo === User profile root ===
dir /ad /b %USERPROFILE%
echo.
echo === Program Files Unity ===
if exist "C:\Program Files\Unity" (dir /s /b "C:\Program Files\Unity\Unity.exe" 2>nul) else echo 없음
echo.
echo === UnityHub AppData ===
if exist "%APPDATA%\UnityHub" (dir /b "%APPDATA%\UnityHub") else echo 없음
echo.
echo === editors-v2.json ===
if exist "%APPDATA%\UnityHub\editors-v2.json" (type "%APPDATA%\UnityHub\editors-v2.json") else echo 없음
echo.
echo === secondaryInstallPath ===
if exist "%APPDATA%\UnityHub\secondaryInstallPath.json" (type "%APPDATA%\UnityHub\secondaryInstallPath.json") else echo 없음
echo.
echo === User Unity folder ===
if exist "%USERPROFILE%\Unity" (dir /s /b "%USERPROFILE%\Unity\Unity.exe" 2>nul) else echo 없음
echo.
echo === 전체 Unity.exe 검색 (5개만) ===
for /f "delims=" %%i in ('where /R C:\ Unity.exe 2^>nul') do @(echo %%i)
