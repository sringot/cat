@echo off
cd /d "%~dp0"

echo Installation / verification des dependances...
python -m pip install websockets qrcode --quiet

echo.
echo Ouverture des ports dans le pare-feu Windows...
netsh advfirewall firewall delete rule name="wt-rotate-ws"   >nul 2>&1
netsh advfirewall firewall delete rule name="wt-rotate-http" >nul 2>&1
netsh advfirewall firewall add rule name="wt-rotate-ws"   protocol=TCP dir=in localport=8765 action=allow >nul
netsh advfirewall firewall add rule name="wt-rotate-http" protocol=TCP dir=in localport=8766 action=allow >nul
echo   Ports 8765 et 8766 ouverts.

echo.
echo Demarrage du serveur wt-rotate Remote Control...
python remote_server.py
pause
