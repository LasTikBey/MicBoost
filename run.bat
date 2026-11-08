@echo off
cd /d "%~dp0"
if not exist .venv (
  py -3 -m venv .venv || goto :err
  call .venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -r requirements.txt || goto :err
) else (
  call .venv\Scripts\activate.bat
)
python main.py
if errorlevel 1 goto :err
exit /b 0
:err
echo.
echo ===== HATA OLUSTU. Yukaridaki kirmizi/ingilizce hata mesajini bana gonderin. =====
echo Ayrica su dosyaya bakin: %%APPDATA%%\MicBoost\micboost.log
pause
exit /b 1
