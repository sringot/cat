@echo off
:: Ce script crée un raccourci dans le dossier Démarrage Windows
:: pour que canva_server.py se lance automatiquement au boot.
:: Lance ce fichier UNE seule fois en tant qu'administrateur.

set "SCRIPT_DIR=%~dp0"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP%\canva_server.lnk"

:: Crée le raccourci via PowerShell
powershell -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$s = $ws.CreateShortcut('%SHORTCUT%');" ^
  "$s.TargetPath = 'pythonw.exe';" ^
  "$s.Arguments = '\"%SCRIPT_DIR%canva_server.py\"';" ^
  "$s.WorkingDirectory = '%SCRIPT_DIR%';" ^
  "$s.WindowStyle = 7;" ^
  "$s.Save()"

if exist "%SHORTCUT%" (
    echo Raccourci créé : %SHORTCUT%
    echo canva_server démarrera automatiquement au prochain boot.
) else (
    echo ERREUR : impossible de créer le raccourci.
)
pause
