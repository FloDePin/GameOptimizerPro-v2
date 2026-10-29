@echo off
:: GameOptimizerPro v2.1 - Launcher
:: Nutzt gezielt die klassische Python-Installation (nicht Store-App) - tools\find_python.cmd.
:: Erster Start / neues Python: fehlt Python, wird die Installation angeboten; fehlende Pakete
:: installiert core\deps.py hier im Fenster (einmalig, mit Fortschritt), dann startet die App.
cd /d "%~dp0"

call "%~dp0tools\find_python.cmd" offer
if not defined PYW (
    pause
    exit /b 1
)

"%PY%" -m core.deps
if errorlevel 1 (
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
