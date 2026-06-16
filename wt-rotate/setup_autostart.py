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
    print('Clic droit sur setup_autostart.bat → Exécuter en tant qu\'administrateur')
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
    'python -m pip install aiohttp qrcode pycaw pywebpush --quiet\n'
    ':: Boucle de relance : si le serveur plante, il repart seul apres 5 s\n'
    ':loop\n'
    'python remote_server.py\n'
    'echo.\n'
    'echo  Serveur arrete — relance dans 5 s (Ctrl+C pour quitter)...\n'
    'timeout /t 5 /nobreak >nul\n'
    'goto loop\n',
    encoding='utf-8'
)
print(f'[1/4] Lanceur créé   : {launcher.name} (relance auto en cas de plantage)')

# ── 2. Empêcher la déconnexion NinjaOne / RMM après 24 h ─────────────────────
# La carte réseau peut se mettre en veille indépendamment du système, ce qui
# coupe les connexions longues (NinjaOne, TeamViewer…) après ~24 h même si la
# veille système est désactivée. Ce bloc la désactive via powercfg.
print()
print('Configuration de la veille réseau…')
nic_cmds = [
    # Empêche la mise en veille de la carte réseau par le gestionnaire d'énergie
    ['powercfg', '/setacvalueindex', 'SCHEME_CURRENT', 'SUB_NONE', 'HYBRIDSLEEP', '0'],
    # Désactive les timers de veille (AC et batterie)
    ['powercfg', '/change', 'standby-timeout-ac', '0'],
    ['powercfg', '/change', 'hibernate-timeout-ac', '0'],
    # Applique le schéma modifié
    ['powercfg', '/setactive', 'SCHEME_CURRENT'],
]
nic_ok = True
for cmd in nic_cmds:
    r0 = subprocess.run(cmd, capture_output=True, text=True)
    if r0.returncode != 0:
        nic_ok = False

# Désactiver la mise en veille de la carte réseau via le Gestionnaire de
# périphériques (PowerManagement) — nécessite devcon ou pnputil.
# Alternative fiable : script PowerShell ciblant tous les adaptateurs Ethernet/Wi-Fi.
ps_nic = (
    "Get-NetAdapter | ForEach-Object {"
    "  try { Disable-NetAdapterPowerManagement -Name $_.Name -WakeOnMagicPacket -WakeOnPattern "
    "        -ErrorAction SilentlyContinue } catch {} }"
)
r_nic = subprocess.run(
    ['powershell', '-NoProfile', '-NonInteractive', '-Command', ps_nic],
    capture_output=True, text=True
)
if nic_ok:
    print('[2/4] Veille réseau  : désactivée (NinjaOne restera connecté)')
else:
    print('[2/4] Veille réseau  : vérifiez manuellement dans les options de l\'adaptateur réseau')

# ── 3. Tâche planifiée (serveur 30 s après le login) ─────────────────────────
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
    print(f'[3/4] Tâche créée    : "{task_name}"')
    print('       Le serveur démarrera 30 s après chaque connexion Windows.')
else:
    print(f'[3/4] ECHEC tâche    : {r.stderr.strip()[:120]}')

# ── 3. Raccourci navigateur dans le dossier Démarrage Windows ────────────────
# Le choix est important : lancer le MAUVAIS navigateur au boot peut faire
# tourner DEUX extensions kiosque en même temps (conflit Chrome + Edge).
print()
print('Quel navigateur fait tourner le kiosque ?')
print('  1. Google Chrome')
print('  2. Microsoft Edge')
choice = input('Choix [1/2, défaut 1] : ').strip() or '1'

BROWSERS = {
    '1': ('Chrome', [
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    ]),
    '2': ('Edge', [
        r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    ]),
}
browser_name, candidates = BROWSERS.get(choice, BROWSERS['1'])
browser_exe = next((p for p in candidates if Path(p).exists()), None)

startup_folder = (
    Path(os.environ['APPDATA'])
    / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'Startup'
)
lnk = startup_folder / 'wt-rotate-browser.lnk'

if browser_exe:
    ps = (
        f"$ws = New-Object -ComObject WScript.Shell; "
        f"$lnk = $ws.CreateShortcut('{lnk}'); "
        f"$lnk.TargetPath = '{browser_exe}'; "
        f"$lnk.Save()"
    )
    r2 = subprocess.run(
        ['powershell', '-NoProfile', '-NonInteractive', '-Command', ps],
        capture_output=True, text=True
    )
    if r2.returncode == 0:
        print(f'[4/4] {browser_name:<14} : raccourci démarrage créé')
    else:
        print(f'[4/4] ECHEC {browser_name} : {r2.stderr.strip()[:80]}')
else:
    print(f'[4/4] {browser_name:<14} : introuvable — ajoutez-le manuellement au dossier Démarrage')

print()
print('═' * 56)
print('Que faire maintenant :')
print()
print('  1. Dans le navigateur, réglez « Au démarrage » sur')
print('     « Ouvrir la page Nouvel onglet » (PAS « Reprendre »,')
print('     sinon une vieille fenêtre kiosque serait restaurée')
print('     en double à chaque redémarrage)')
print('  2. Windows + R → netplwiz → décochez « Les utilisateurs')
print('     doivent entrer un nom d\'utilisateur… » (login auto)')
print('  3. Laissez la rotation ACTIVE puis redémarrez pour tester')
print('  4. Le serveur démarre 30 s après la session')
print('     (le temps que le réseau soit dispo)')
print('═' * 56)
input('\nAppuyez sur Entrée pour quitter...')
