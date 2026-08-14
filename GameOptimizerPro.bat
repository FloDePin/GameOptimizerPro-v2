@echo off
:: GameOptimizerPro v2.1 - Launcher
:: Nutzt gezielt die klassische Python-Installation (nicht Store-App)
cd /d "%~dp0"

:: Reihenfolge wichtig: Zuerst klassische Python-Installationen, DANN erst PATH.
:: WindowsApps-Version (Store) wird ignoriert, weil UAC dort python.exe statt pythonw.exe startet.
set "PYW="
if exist "C:\Python314\pythonw.exe"      set "PYW=C:\Python314\pythonw.exe"
if not defined PYW if exist "C:\Python313\pythonw.exe"      set "PYW=C:\Python313\pythonw.exe"
if not defined PYW if exist "C:\Python312\pythonw.exe"      set "PYW=C:\Python312\pythonw.exe"
if not defined PYW if exist "C:\Program Files\Python314\pythonw.exe" set "PYW=C:\Program Files\Python314\pythonw.exe"
if not defined PYW if exist "C:\Program Files\Python313\pythonw.exe" set "PYW=C:\Program Files\Python313\pythonw.exe"
if not defined PYW if exist "C:\Program Files\Python312\pythonw.exe" set "PYW=C:\Program Files\Python312\pythonw.exe"
if not defined PYW if exist "%LOCALAPPDATA%\Programs\Python\Python314\pythonw.exe" set "PYW=%LOCALAPPDATA%\Programs\Python\Python314\pythonw.exe"
if not defined PYW if exist "%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe" set "PYW=%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe"
if not defined PYW if exist "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe" set "PYW=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"

:: Letzter Fallback: PATH-Suche, aber Store-Variante ausschliessen
if not defined PYW (
    for /f "delims=" %%i in ('where pythonw.exe 2^>nul') do (
        set "CANDIDATE=%%i"
        echo %%i | findstr /I "WindowsApps" >nul
        if errorlevel 1 (
            if not defined PYW set "PYW=%%i"
        )
    )
)

if not defined PYW (
    echo Keine klassische pythonw.exe gefunden.
    echo Bitte Python von python.org installieren, nicht aus dem Microsoft Store.
    pause
    exit /b 1
)

:: Starte pythonw mit Admin-Rechten
:: -Verb RunAs = UAC-Prompt
:: pythonw.exe hat ohnehin kein Konsolenfenster - -WindowStyle Hidden hier wuerde
:: als SW_HIDE-Hint an den neuen Prozess durchgereicht und auch das allererste
:: Fenster (das Tkinter-Hauptfenster) unsichtbar starten. Daher NICHT auf den
:: inneren Start-Process anwenden - nur der aeussere powershell-Aufruf braucht
:: -WindowStyle Hidden, um sein eigenes (leeres) Konsolenfenster zu verstecken.
powershell -NoProfile -WindowStyle Hidden -Command "Start-Process -FilePath '%PYW%' -ArgumentList '\"%~dp0GameOptimizerPro.py\"' -Verb RunAs -WorkingDirectory '%~dp0'"
