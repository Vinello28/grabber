@echo off
REM Grabber Launcher for Windows

cd /d "%~dp0"

echo ============================================================
echo ⚡ Avvio di Grabber (Windows)...
echo ============================================================

IF EXIST ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

where python >nul 2>nul
IF %ERRORLEVEL% NEQ 0 (
    echo Errore: Python non trovato nel sistema. Installa Python 3.10 o superiore.
    pause
    exit /b 1
)

python run.py
pause
