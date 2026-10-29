@echo off
:: Finds the classic python.org Python for GameOptimizerPro.bat and install.bat - NOT the
:: Microsoft Store one (UAC starts python.exe there instead of pythonw.exe, and pip installs
:: into another folder). Sets PYW (pythonw.exe) and PY (python.exe); both empty without one.
:: Argument "offer": when there is none, offer to install Python 3.12 with winget (asks first).
set "PYW="
set "PY="
call :search
if not defined PYW if /I "%~1"=="offer" call :offer
if defined PYW set "PY=%PYW:pythonw.exe=python.exe%"
exit /b 0

:search
for %%V in (314 313 312) do if not defined PYW if exist "C:\Python%%V\pythonw.exe" set "PYW=C:\Python%%V\pythonw.exe"
for %%V in (314 313 312) do if not defined PYW if exist "%ProgramFiles%\Python%%V\pythonw.exe" set "PYW=%ProgramFiles%\Python%%V\pythonw.exe"
for %%V in (314 313 312) do if not defined PYW if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\pythonw.exe" set "PYW=%LOCALAPPDATA%\Programs\Python\Python%%V\pythonw.exe"
:: the Python install manager (python.org's installer since 3.14)
for %%V in (3.14 3.13 3.12) do if not defined PYW if exist "%LOCALAPPDATA%\Python\pythoncore-%%V-64\pythonw.exe" set "PYW=%LOCALAPPDATA%\Python\pythoncore-%%V-64\pythonw.exe"
:: last resort: PATH, but never the Store variant (WindowsApps)
if not defined PYW (
    for /f "delims=" %%i in ('where pythonw.exe 2^>nul') do (
        echo %%i | findstr /I "WindowsApps" >nul
        if errorlevel 1 if not defined PYW set "PYW=%%i"
    )
)
exit /b 0

:offer
echo.
echo  GameOptimizerPro needs Python 3 (free, from python.org).
echo  GameOptimizerPro braucht Python 3 (kostenlos, von python.org).
echo.
where winget >nul 2>nul
if errorlevel 1 goto :manual
choice /C JYN /M "Install Python 3.12 automatically now? / Python 3.12 jetzt automatisch installieren? (J/Y = yes/ja, N = no/nein)"
if errorlevel 3 goto :manual
echo.
echo  Installing Python 3.12 (one time) ... / Installiere Python 3.12 (einmalig) ...
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
call :search
if not defined PYW winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
if not defined PYW call :search
if defined PYW exit /b 0
echo.
echo  Python could not be installed automatically. / Python konnte nicht automatisch installiert werden.
:manual
echo  Please install Python from python.org (not from the Microsoft Store), then start again.
echo  Bitte Python von python.org installieren (nicht aus dem Microsoft Store), dann neu starten.
start "" "https://www.python.org/downloads/windows/"
exit /b 0
