@echo off
cd /d "%~dp0"

:: ── Vérification des droits administrateur ────────────────────────────────────
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [ERREUR] Ce script doit etre lance en tant qu'Administrateur.
    echo.
    echo  Clic droit sur start_remote.bat
    echo  puis "Executer en tant qu'administrateur"
    echo.
    pause
    exit /b 1
)

echo Installation / verification des dependances...
python -m pip install aiohttp qrcode pycaw --quiet

echo.
echo Ouverture du port 8765 dans le pare-feu Windows...
netsh advfirewall firewall delete rule name="wt-rotate"      >nul 2>&1
netsh advfirewall firewall delete rule name="wt-rotate-ws"   >nul 2>&1
netsh advfirewall firewall delete rule name="wt-rotate-http" >nul 2>&1
netsh advfirewall firewall add rule name="wt-rotate" protocol=TCP dir=in localport=8765 action=allow >nul
echo   Port 8765 ouvert (HTTP + WebSocket sur le meme port).

echo.
echo Demarrage du serveur wt-rotate Remote Control...
python remote_server.py
pause
