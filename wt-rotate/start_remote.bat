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
python -m pip install aiohttp qrcode pycaw anthropic cryptography --quiet

:: ── Assistant vocal IA : cle API lue depuis cle_ia.txt (si present) ────────────
:: Ouvrez cle_ia.txt avec Notepad, remplacez le texte par votre cle Anthropic
:: (commence par sk-ant-...) puis sauvegardez. Relancez ce script ensuite.
if defined ANTHROPIC_API_KEY goto :key_done
if not exist "cle_ia.txt" (
    echo   Assistant vocal IA : desactive ^(fichier cle_ia.txt introuvable^)
    goto :key_done
)
for /f "usebackq delims=" %%K in ("cle_ia.txt") do set "ANTHROPIC_API_KEY=%%K"
:: 'if errorlevel 1' teste le code APRES findstr (contrairement a %errorlevel%
:: entre parentheses, fige au parsing) — commence par sk- = cle plausible
echo %ANTHROPIC_API_KEY% | findstr /b "sk-" >nul 2>&1
if errorlevel 1 (
    echo   [!] cle_ia.txt trouvee mais la cle ne semble pas valide ^(sk-ant-...^).
    set "ANTHROPIC_API_KEY="
) else (
    echo   Assistant vocal IA : cle chargee depuis cle_ia.txt [OK]
)
:key_done

:: ── Micro vocal : cle Groq lue depuis cle_groq.txt (transcription audio) ───────
:: Ouvrez cle_groq.txt avec Notepad, collez votre cle Groq (https://console.groq.com,
:: gratuit, commence par gsk_) puis sauvegardez. Sans ce fichier, l'assistant
:: reste pilotable au texte mais pas au micro.
if defined GROQ_API_KEY goto :groq_done
if not exist "cle_groq.txt" (
    echo   Micro vocal : desactive ^(fichier cle_groq.txt introuvable^)
    goto :groq_done
)
for /f "usebackq delims=" %%K in ("cle_groq.txt") do set "GROQ_API_KEY=%%K"
echo %GROQ_API_KEY% | findstr /b "gsk_" >nul 2>&1
if errorlevel 1 (
    echo   [!] cle_groq.txt trouvee mais la cle ne semble pas valide ^(gsk_...^).
    set "GROQ_API_KEY="
) else (
    echo   Micro vocal : cle Groq chargee depuis cle_groq.txt [OK]
)
:groq_done

echo.
echo Ouverture des ports 8765 et 8766 dans le pare-feu Windows...
netsh advfirewall firewall delete rule name="wt-rotate"      >nul 2>&1
netsh advfirewall firewall delete rule name="wt-rotate-ws"   >nul 2>&1
netsh advfirewall firewall delete rule name="wt-rotate-http" >nul 2>&1
netsh advfirewall firewall delete rule name="wt-rotate-https" >nul 2>&1
netsh advfirewall firewall add rule name="wt-rotate" protocol=TCP dir=in localport=8765 action=allow >nul
netsh advfirewall firewall add rule name="wt-rotate-https" protocol=TCP dir=in localport=8766 action=allow >nul
echo   Ports 8765 (HTTP) et 8766 (HTTPS micro) ouverts.

echo.
echo Demarrage du serveur wt-rotate Remote Control...
echo (relance automatique en cas de plantage — Ctrl+C pour quitter)
:loop
python remote_server.py
echo.
echo  Serveur arrete — relance dans 5 s (Ctrl+C pour quitter)...
timeout /t 5 /nobreak >nul
goto loop
