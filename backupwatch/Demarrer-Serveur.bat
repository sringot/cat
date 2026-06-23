@echo off
chcp 65001 >nul
cd /d "%~dp0"
title BackupWatch - Serveur kiosque
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo.
echo   ===========================================
echo     BackupWatch - Serveur kiosque
echo   ===========================================
echo.
echo   Le tableau de bord reste servi sur une URL fixe et se
echo   regenere automatiquement chaque matin a 7h00.
echo.
echo   URL a coller dans wee rotate : http://localhost:8470/
echo.
echo   Laissez cette fenetre ouverte. Ctrl+C pour arreter.
echo.

REM Choisit la commande Python disponible
set "PY=python"
where python >nul 2>nul || set "PY=py"

%PY% -m backupwatch --serve --source graph

echo.
echo   Serveur arrete.
pause
