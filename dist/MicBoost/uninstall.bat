@echo off
setlocal

if exist "%~dp0unins000.exe" (
  start "" "%~dp0unins000.exe"
  exit /b 0
)

for %%I in ("%~dp0.") do set "APP_FOLDER=%%~nxI"
if /I not "%APP_FOLDER%"=="MicBoost" (
  echo Refusing to remove this folder. Portable uninstall only works from a folder named MicBoost.
  pause
  exit /b 1
)
if not exist "%~dp0MicBoost.exe" (
  echo MicBoost.exe was not found beside this script.
  pause
  exit /b 1
)

tasklist /FI "IMAGENAME eq MicBoost.exe" /NH | find /I "MicBoost.exe" >nul
if not errorlevel 1 (
  echo Close MicBoost before uninstalling it, then run this file again.
  pause
  exit /b 1
)

echo This removes only the MicBoost application folder.
echo Your settings in %APPDATA%\MicBoost will be kept.
choice /C YN /M "Continue with removal"
if errorlevel 2 exit /b 0

set "APP_DIR=%~dp0"
if "%APP_DIR:~-1%"=="\" set "APP_DIR=%APP_DIR:~0,-1%"
set "CLEANUP=%TEMP%\micboost-uninstall-%RANDOM%.cmd"
> "%CLEANUP%" echo @echo off
>> "%CLEANUP%" echo timeout /t 2 /nobreak ^>nul
>> "%CLEANUP%" echo rmdir /s /q "%APP_DIR%"
>> "%CLEANUP%" echo del "%%~f0"
start "" /b "%ComSpec%" /c ""%CLEANUP%""
exit /b 0