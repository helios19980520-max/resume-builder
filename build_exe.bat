@echo off
REM ============================================================================
REM  Build ResumeBuilder.exe (Windows). Requirements on this PC:
REM    - Python 3.11 or 3.12  (https://www.python.org/downloads/  tick "Add python.exe to PATH")
REM    - Node.js 18+           (https://nodejs.org  LTS installer)
REM  Keys: ANTHROPIC_API_KEY / TAVILY_API_KEY in .env next to this file are baked into the exe
REM        as defaults (users can still override them in the app's Settings screen).
REM  Output: dist\ResumeBuilder.exe   (single file, ~120 MB)
REM ============================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
set LOG=%~dp0build_log.txt
echo Build started %date% %time% > "%LOG%"

echo.
echo ==== Checking tools ====
REM Find a real Python 3.11/3.12, skipping the Microsoft Store placeholder that only prints "Python was not found".
set "PY="
for %%C in ("py -3.12" "py -3.11" "py -3") do (
  if not defined PY (
    %%~C -c "import sys" >nul 2>nul && set "PY=%%~C"
  )
)
if not defined PY (
  for %%P in ("%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" "%ProgramFiles%\Python312\python.exe" "%ProgramFiles%\Python311\python.exe" "C:\Python312\python.exe" "C:\Python311\python.exe") do (
    if not defined PY if exist %%P set PY="%%~P"
  )
)
if not defined PY (
  python -c "import sys" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo [ERROR] No working Python found. Install Python 3.12 from python.org ^(64-bit installer, tick "Add python.exe to PATH"^).
  echo         If it is installed, disable the Store aliases: Settings ^> Apps ^> Advanced app settings ^> App execution aliases ^> turn off python.exe and python3.exe
  goto :fail
)
for /f "tokens=*" %%v in ('%PY% --version 2^>^&1') do echo Found %%v  ^(%PY%^)
where npm >nul 2>nul || (echo [ERROR] Node.js/npm not found. Install Node.js LTS from nodejs.org, then run this again. & goto :fail)
for /f "tokens=*" %%v in ('node --version 2^>^&1') do echo Found Node %%v

echo.
echo ==== [1/5] Building the web UI (1-2 min) ====
pushd frontend
call npm install --no-audit --no-fund >> "%LOG%" 2>&1 || (popd & echo [ERROR] npm install failed - see build_log.txt & goto :fail)
call npm run build >> "%LOG%" 2>&1 || (popd & echo [ERROR] npm run build failed - see build_log.txt & goto :fail)
popd
if exist backend\static rmdir /s /q backend\static
xcopy /e /i /q frontend\dist backend\static >nul || (echo [ERROR] could not copy the built UI & goto :fail)

echo.
echo ==== [2/5] Baking API keys from .env ====
%PY% tools\bake_keys.py || (echo [ERROR] bake_keys failed & goto :fail)

echo.
echo ==== [3/5] Installing Python dependencies (2-4 min first time) ====
if not exist backend\.venv %PY% -m venv backend\.venv || (echo [ERROR] could not create venv & goto :fail)
call backend\.venv\Scripts\activate.bat
python -m pip install --upgrade pip >> "%LOG%" 2>&1
pip install -r backend\requirements.txt pyinstaller >> "%LOG%" 2>&1 || (echo [ERROR] pip install failed - see build_log.txt & goto :fail)

echo.
echo ==== [4/5] Building the executable with PyInstaller (2-5 min) ====
pushd backend
pyinstaller --noconfirm --clean resume_builder.spec >> "%LOG%" 2>&1 || (popd & echo [ERROR] PyInstaller failed - see build_log.txt & goto :fail)
popd

echo.
echo ==== [5/5] Done ====
if not exist dist mkdir dist
copy /y backend\dist\ResumeBuilder.exe dist\ResumeBuilder.exe >nul || (echo [ERROR] exe not found after build - see build_log.txt & goto :fail)
echo.
echo   SUCCESS:  %~dp0dist\ResumeBuilder.exe
echo   Double-click it; the app opens in your browser. Keep its window open while using the app.
echo.
pause
exit /b 0

:fail
echo.
echo   Build did not finish. Full log: %LOG%
echo   Send the last lines of build_log.txt and this window's text to get it fixed.
echo.
pause
exit /b 1