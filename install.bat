@echo off
title GameOptimizerPro - Installer
color 0B
echo.
echo  ==========================================
echo    GameOptimizerPro - Installing Dependencies
echo  ==========================================
echo.

:: WICHTIG: dieselbe klassische Python-Installation finden wie der Launcher
:: (GameOptimizerPro.bat), damit die Module NICHT in der Microsoft-Store-Version
:: landen und die App danach mit ModuleNotFoundError abstuerzt.
:: Reihenfolge = exakt wie im Launcher, nur python.exe statt pythonw.exe.
set "PY="
if exist "C:\Python314\python.exe"      set "PY=C:\Python314\python.exe"
if not defined PY if exist "C:\Python313\python.exe"      set "PY=C:\Python313\python.exe"
if not defined PY if exist "C:\Python312\python.exe"      set "PY=C:\Python312\python.exe"
if not defined PY if exist "C:\Program Files\Python314\python.exe" set "PY=C:\Program Files\Python314\python.exe"
if not defined PY if exist "C:\Program Files\Python313\python.exe" set "PY=C:\Program Files\Python313\python.exe"
if not defined PY if exist "C:\Program Files\Python312\python.exe" set "PY=C:\Program Files\Python312\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"

:: Fallback: PATH-Suche, aber Store-Variante (WindowsApps) ausschliessen
if not defined PY (
    for /f "delims=" %%i in ('where python.exe 2^>nul') do (
        echo %%i | findstr /I "WindowsApps" >nul
        if errorlevel 1 (
            if not defined PY set "PY=%%i"
        )
    )
)

if not defined PY (
    echo [ERROR] Keine klassische python.exe gefunden.
    echo Bitte Python von python.org installieren ^(nicht aus dem Microsoft Store^).
    pause
    exit /b 1
)

echo  Python: %PY%
"%PY%" --version
echo.

echo [1/2] pip upgrade...
"%PY%" -m pip install --upgrade pip -q

echo [2/2] Installing dependencies from requirements.txt...
"%PY%" -m pip install -r "%~dp0requirements.txt" -q

echo.
echo  ==========================================
echo   Done! Optional CUDA stress test:
echo     "%PY%" -m pip install cupy-cuda12x
echo  ==========================================
echo.
echo  Before first run - Afterburner setup:
echo    Settings ^> General:
echo      [x] Unlock voltage control ^> Standard MSI
echo      [x] Unlock voltage monitoring
echo    Settings ^> Monitoring ^> GPU voltage: [x]
echo    Profile slot 2-5: unlock the padlock icon
echo.
echo  Start with: GameOptimizerPro.bat
echo.
pause
