@echo off
setlocal

echo This removes only the Python virtual environments created by run.bat and build.bat:
echo   %~dp0.venv
echo   %~dp0.venv-build
echo.
echo Project files, dist/build outputs, system Python, Inno Setup, and MicBoost settings are kept.
choice /C YN /M "Continue with removal"
if errorlevel 2 exit /b 0

set "FAILED="
for %%D in (.venv .venv-build) do (
  if exist "%~dp0%%D\" (
    echo Removing %%D...
    rmdir /s /q "%~dp0%%D"
    if exist "%~dp0%%D\" set "FAILED=1"
  ) else (
    echo %%D not found; skipping.
  )
)

if defined FAILED (
  echo.
  echo ERROR: One or more environments could not be removed.
  echo Close MicBoost, Python, and terminals using these environments, then try again.
  exit /b 1
)

echo.
echo The selected virtual environments have been removed.
exit /b 0
