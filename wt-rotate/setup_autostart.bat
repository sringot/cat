@echo off
cd /d "%~dp0"

:: ── Vérification des droits administrateur ────────────────────────────────────
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [ERREUR] Ce script doit etre lance en tant qu'Administrateur.
    echo.
    echo  Clic droit sur setup_autostart.bat
    echo  puis "Executer en tant qu'administrateur"
    echo.
    pause
    exit /b 1
)

python setup_autostart.py
