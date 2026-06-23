@echo off
chcp 65001 >nul
cd /d "%~dp0"
title BackupWatch - Supervision des sauvegardes
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo.
echo   ===========================================
echo     BackupWatch - Supervision des sauvegardes
echo   ===========================================
echo.
echo   Connexion a la boite et analyse en cours...
echo.

REM Choisit la commande Python disponible
set "PY=python"
where python >nul 2>nul || set "PY=py"

%PY% -m backupwatch --source graph --open
set "RC=%errorlevel%"

echo.
if "%RC%"=="0" echo   [OK] Tableau de bord genere et ouvert dans le navigateur.
if "%RC%"=="2" echo   [OK] Genere et ouvert -- ATTENTION : au moins une sauvegarde en ECHEC (voir le dashboard).
if not "%RC%"=="0" if not "%RC%"=="2" echo   [PROBLEME] Le scan n'a pas abouti (code %RC%). Verifie le message ci-dessus + le fichier .env.
echo.
pause
