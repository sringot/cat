@echo off
cd /d "%~dp0"
echo Installation / verification des dependances...
python -m pip install websockets qrcode --quiet
echo.
echo Demarrage du serveur wt-rotate Remote Control...
python remote_server.py
pause
