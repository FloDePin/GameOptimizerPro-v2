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
echo   GPU-Stresstest fuer den Auto-Tuner (NVIDIA)
echo  ==========================================
echo   Der Auto-Tuner braucht echte GPU-Last. Dafuer gibt es 'cupy'
echo   (ca. 1-2 GB Download, kein CUDA-Toolkit noetig). Ohne cupy geht
echo   der Tuner nur mit parallel laufendem FurMark.
echo.
choice /C JN /M "cupy jetzt installieren (J = ja, N = nein)"
if not errorlevel 2 (
    echo [optional] Installing cupy-cuda12x[ctk] ...
    "%PY%" -m pip install "cupy-cuda12x[ctk]"
)
echo.
echo  ==========================================
echo   Fertig! Afterburner einrichten (einmalig):
echo  ==========================================
echo    Einstellungen ^> Allgemein:
echo      [x] Spannungssteuerung freischalten
echo      [x] Spannungsueberwachung freischalten
echo      [x] Minimiert starten (empfohlen)
echo    Einstellungen ^> Ueberwachung: [x] GPU-Spannung, [x] Leistung
echo    Nichts verstellen, dann Speichern ^> Slot 1 klicken
echo    Details: TESTANLEITUNG.md
echo.
echo  Start with: GameOptimizerPro.bat
echo.
pause
