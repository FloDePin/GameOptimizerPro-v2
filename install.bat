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
    echo [ERROR] No classic python.exe found - install Python from python.org ^(not from the Microsoft Store^).
    echo [FEHLER] Keine klassische python.exe gefunden - Python von python.org installieren ^(nicht aus dem Microsoft Store^).
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
echo   GPU load for the auto-tuner (NVIDIA) / GPU-Last fuer den Auto-Tuner
echo  ==========================================
echo   The tuner needs real GPU load: 'cupy' (about 1-2 GB, no CUDA toolkit needed).
echo   Der Tuner braucht echte GPU-Last: 'cupy' (ca. 1-2 GB, kein CUDA-Toolkit noetig).
echo.
choice /C JYN /M "Install cupy now? / cupy jetzt installieren? (J/Y = yes/ja, N = no/nein)"
if not errorlevel 3 (
    echo [optional] Installing cupy-cuda12x[ctk] ...
    "%PY%" -m pip install "cupy-cuda12x[ctk]"
)
echo.
echo  ==========================================
echo   Done! Set up MSI Afterburner once / Afterburner einmalig einrichten:
echo  ==========================================
echo    Settings ^> General / Einstellungen ^> Allgemein:
echo      [x] Unlock voltage control / Spannungssteuerung freischalten
echo      [x] Unlock voltage monitoring / Spannungsueberwachung freischalten
echo      [x] Start minimized / Minimiert starten (recommended / empfohlen)
echo    Settings ^> Monitoring / Ueberwachung: [x] GPU voltage / GPU-Spannung, [x] Power / Leistung
echo    Change nothing, click Save, then slot 1 / Nichts verstellen, Speichern, dann Slot 1
echo    Details: README.md (Setting up MSI Afterburner)
echo.
echo  Start with / Starten mit: GameOptimizerPro.bat
echo.
pause
