@echo off
REM MicBoost - EXE ve (varsa) kurulum dosyasi uretir. Windows 10/11 + 64-bit Python gerekir.
setlocal
cd /d "%~dp0"

set "NEED_INSTALL="
if not exist .venv-build\Scripts\python.exe (
  py -3 -m venv .venv-build || goto :err
  set "NEED_INSTALL=1"
)
call .venv-build\Scripts\activate.bat
if not exist ".venv-build\requirements.txt" set "NEED_INSTALL=1"
if not exist ".venv-build\requirements-dev.txt" set "NEED_INSTALL=1"
fc /b requirements.txt .venv-build\requirements.txt >nul 2>nul
if errorlevel 1 set "NEED_INSTALL=1"
fc /b requirements-dev.txt .venv-build\requirements-dev.txt >nul 2>nul
if errorlevel 1 set "NEED_INSTALL=1"
if defined NEED_INSTALL (
  python -m pip install --upgrade pip || goto :err
  pip install -r requirements-dev.txt || goto :err
  copy /y requirements.txt .venv-build\requirements.txt >nul || goto :err
  copy /y requirements-dev.txt .venv-build\requirements-dev.txt >nul || goto :err
)

echo.
echo === Testler ===
python tests\test_dsp.py || goto :err
python tests\test_engine_mock.py || goto :err

echo.
echo === EXE olusturuluyor (PyInstaller) ===
if exist "dist\MicBoost.exe" del /f /q "dist\MicBoost.exe" >nul
if exist "dist\MicBoost" rmdir /s /q "dist\MicBoost" >nul
if exist "build\micboost" rmdir /s /q "build\micboost" >nul
pyinstaller packaging\micboost.spec --noconfirm --clean || goto :err
copy /y packaging\uninstall.bat dist\MicBoost\uninstall.bat >nul || goto :err
copy /y dist\MicBoost\MicBoost.exe dist\MicBoost.exe >nul || goto :err
if exist "dist\_internal" rmdir /s /q "dist\_internal" >nul
robocopy "dist\MicBoost\_internal" "dist\_internal" /E /NFL /NDL /NJH /NJS /NC /NS >nul
if errorlevel 8 goto :err
echo EXE: dist\MicBoost.exe
echo EXE klasoru: dist\MicBoost\MicBoost.exe

echo.
echo === Kurulum dosyasi (Inno Setup 6) ===
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" (
  "%ISCC%" packaging\installer.iss || goto :err
  echo Kurulum dosyasi: dist\MicBoost-Setup-1.0.0.exe
) else (
  echo Inno Setup 6 bulunamadi; yalnizca EXE klasoru uretildi. https://jrsoftware.org/isdl.php
)
echo.
echo Bitti.
exit /b 0
:err
echo.
echo HATA: build basarisiz oldu.
if /I "%~1"=="--no-pause" exit /b 1
pause
exit /b 1
