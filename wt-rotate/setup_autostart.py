#!/usr/bin/env python3
"""
Configure le démarrage automatique de wt-rotate sur Windows.
Lancez ce script UNE FOIS en tant qu'Administrateur.
"""
import os, sys, subprocess, platform
from pathlib import Path

if platform.system() != 'Windows':
    print('Ce script est uniquement pour Windows.')
    input('Appuyez sur Entrée...')
    sys.exit(1)

import ctypes
if not ctypes.windll.shell32.IsUserAnAdmin():
    print('[ERREUR] Ce script doit être lancé en tant qu\'Administrateur.')
    print('Clic droit sur setup_autostart.py → Exécuter en tant qu\'administrateur')
    input('\nAppuyez sur Entrée pour quitter...')
    sys.exit(1)

here = Path(__file__).parent.resolve()

print('═' * 56)
print('  wt-rotate — Configuration du démarrage automatique')
print('═' * 56)
print()

# ── 1. Lanceur silencieux pour le Task Scheduler ──────────────────────────────
launcher = here / '_autostart_launcher.bat'
launcher.write_text(
    '@echo off\n'
    f'cd /d "{here}"\n'
    'python -m pip install aiohttp qrcode pycaw --quiet\n'
    'python remote_server.py\n',
    encoding='utf-8'
)
print(f'[1/3] Lanceur créé   : {launcher.name}')

# ── 2. Tâche planifiée (serveur 30 s après le login) ─────────────────────────
task_name = 'wt-rotate serveur'
r = subprocess.run([
    'schtasks', '/create',
    '/tn', task_name,
    '/tr', f'cmd /k "{launcher}"',
    '/sc', 'ONLOGON',
    '/rl', 'HIGHEST',
    '/delay', '0000:30',
    '/f'
], capture_output=True, text=True)
if r.returncode == 0:
    print(f'[2/3] Tâche créée    : "{task_name}"')
    print('       Le serveur démarrera 30 s après chaque connexion Windows.')
else:
    print(f'[2/3] ECHEC tâche    : {r.stderr.strip()[:120]}')

# ── 3. Raccourci Chrome dans le dossier Démarrage Windows ────────────────────
startup_folder = (
    Path(os.environ['APPDATA'])
    / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'Startup'
)
lnk = startup_folder / 'wt-rotate-chrome.lnk'
chrome_candidates = [
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
]
chrome_exe = next((p for p in chrome_candidates if Path(p).exists()), None)

if chrome_exe:
    ps = (
        f"$ws = New-Object -ComObject WScript.Shell; "
        f"$lnk = $ws.CreateShortcut('{lnk}'); "
        f"$lnk.TargetPath = '{chrome_exe}'; "
        f"$lnk.Save()"
    )
    r2 = subprocess.run(
        ['powershell', '-NoProfile', '-NonInteractive', '-Command', ps],
        capture_output=True, text=True
    )
    if r2.returncode == 0:
        print(f'[3/3] Chrome         : raccourci démarrage créé')
    else:
        print(f'[3/3] ECHEC Chrome   : {r2.stderr.strip()[:80]}')
else:
    print('[3/3] Chrome         : introuvable — ajoutez-le manuellement au dossier Démarrage')

print()
print('═' * 56)
print('Que faire maintenant :')
print()
print('  1. Redémarrez Windows pour tester')
print('  2. Si la rotation était active avant la coupure,')
print('     elle redémarrera automatiquement quand Chrome s\'ouvre')
print('  3. Le serveur démarre 30 s après votre session')
print('     (le temps que le réseau WiFi soit dispo)')
print('═' * 56)
input('\nAppuyez sur Entrée pour quitter...')
