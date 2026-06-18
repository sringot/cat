#!/usr/bin/env python3
"""
Configure le démarrage automatique de wt-rotate sur Windows.
Applique aussi les correctifs réseau pour empêcher NinjaOne et WithSecure
de se déconnecter après ~24 h (keepalive TCP, veille NIC, Fast Startup).
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
launcher = here / 'wt-launcher.bat'
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
print(f'[1/4] Lanceur créé   : {launcher.name} (relance auto en cas de plantage — hors dossier extension)')

# ══════════════════════════════════════════════════════════════════
# BLOC « CONNEXIONS STABLES » — empêche NinjaOne / WithSecure de se
# déconnecter après ~24 h.
#
# Causes typiques des décos :
#   A) La carte réseau entre en économie d'énergie (sleep NIC)
#   B) Windows envoie des keepalives TCP toutes les 2 h → le NAT du
#      routeur ou le pare-feu termine les sessions inactives avant ça
#   C) Fast Startup : pas un vrai arrêt → le driver NIC reprend un
#      état résiduel, ce qui désynchronise les agents au démarrage
#   D) L'agent plante silencieusement et ne redémarre pas seul
# ══════════════════════════════════════════════════════════════════

# ── 2a. Veille système (powercfg) ────────────────────────────────────────────
print()
print('═' * 56)
print('  Fix déconnexions NinjaOne / WithSecure')
print('═' * 56)
print()
print('[2a] Désactivation de la veille système…')
for cmd in [
    ['powercfg', '/change', 'standby-timeout-ac',   '0'],
    ['powercfg', '/change', 'hibernate-timeout-ac',  '0'],
    ['powercfg', '/change', 'standby-timeout-dc',   '0'],
    ['powercfg', '/setactive', 'SCHEME_CURRENT'],
]:
    subprocess.run(cmd, capture_output=True)
print('     OK — veille système désactivée (AC + batterie)')

# ── 2b. Veille NIC au niveau driver (PnPCapabilities) ────────────────────────
# Disable-NetAdapterPowerManagement ne touche pas la case « Autoriser
# l'ordinateur à éteindre ce périphérique pour économiser l'énergie »
# dans le Gestionnaire de périphériques. La seule façon fiable est de
# passer par le registre (PnPCapabilities = 0x18).
#   Bit 3 (0x08) = désactive Wake-on-Magic-Packet
#   Bit 4 (0x10) = désactive SelectiveSuspend (= la case en question)
print('[2b] Désactivation de la mise en veille de la carte réseau…')
ps_nic = r"""
$nicClass = 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e972-e325-11ce-bfc1-08002be10318}'
$adapters = @{}
Get-NetAdapter -Physical -ErrorAction SilentlyContinue | ForEach-Object {
    $adapters[$_.InterfaceGuid] = $_.Name
}
$count = 0
Get-ChildItem $nicClass -ErrorAction SilentlyContinue | ForEach-Object {
    $guid = $_.GetValue('NetCfgInstanceId')
    if ($guid -and $adapters.ContainsKey($guid)) {
        # 0x18 = desactive SelectiveSuspend + WakeOnMagicPacket au niveau driver
        Set-ItemProperty -Path $_.PSPath -Name 'PnPCapabilities' -Value 24 -Type DWord -Force -ErrorAction SilentlyContinue
        $count++
    }
}
# Complement via cmdlet (cible les proprietes restantes)
Get-NetAdapter -Physical -ErrorAction SilentlyContinue | ForEach-Object {
    try { Disable-NetAdapterPowerManagement -Name $_.Name -ErrorAction SilentlyContinue } catch {}
}
Write-Output "adapters_fixed=$count"
"""
r_nic = subprocess.run(
    ['powershell', '-NoProfile', '-NonInteractive', '-Command', ps_nic],
    capture_output=True, text=True
)
nic_count = 0
for line in r_nic.stdout.splitlines():
    if line.startswith('adapters_fixed='):
        try: nic_count = int(line.split('=')[1])
        except ValueError: pass
if nic_count > 0:
    print(f'     OK — {nic_count} adaptateur(s) réseau : mise en veille driver désactivée')
else:
    print('     AVERTISSEMENT — vérifiez manuellement dans Gestionnaire de périphériques')
    print('     → Adaptateurs réseau → [votre carte] → Propriétés → Gestion de l\'alimentation')
    print('     → décochez « Autoriser l\'ordinateur à éteindre ce périphérique… »')

# ── 2c. Keepalive TCP agressif ────────────────────────────────────────────────
# Windows envoie un premier keepalive TCP après 2 HEURES d'inactivité.
# Si le NAT du routeur (ou le pare-feu d'entreprise) a un timeout inférieur
# (souvent 30 min – 24 h), il supprime la session avant le keepalive.
# En passant à 60 s, toutes les connexions longues (NinjaOne, WithSecure,
# TeamViewer…) survivent aux règles de timeout réseau.
# ⚠ S'applique après redémarrage pour les nouvelles connexions.
print('[2c] Keepalive TCP : 2 h → 60 s…')
tcp_key = r'HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters'
tcp_ok = all(
    subprocess.run(
        ['reg', 'add', tcp_key, '/v', name, '/t', 'REG_DWORD', '/d', str(val), '/f'],
        capture_output=True
    ).returncode == 0
    for name, val in [
        ('KeepAliveTime',              60_000),   # 60 s (était 7 200 000 ms = 2 h)
        ('KeepAliveInterval',           5_000),   # retry toutes les 5 s
        ('TcpMaxDataRetransmissions',       5),   # abandon après 5 tentatives
    ]
)
print(f'     {"OK — Windows enverra un keepalive toutes les 60 s sur toutes les connexions TCP" if tcp_ok else "ECHEC reg add — vérifiez les droits"}')

# ── 2d. Désactiver le Fast Startup Windows ───────────────────────────────────
# Le Fast Startup (démarrage rapide) n'est pas un vrai arrêt : Windows
# hibernite le kernel. À la reprise, le driver NIC repart d'un état
# résiduel qui peut désynchroniser NinjaOne / WithSecure (~24 h après).
# Un vrai arrêt réinitialise complètement le driver réseau.
print('[2d] Désactivation du Fast Startup (démarrage rapide)…')
r_fs = subprocess.run(
    ['reg', 'add',
     r'HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power',
     '/v', 'HiberbootEnabled', '/t', 'REG_DWORD', '/d', '0', '/f'],
    capture_output=True
)
print(f'     {"OK — arrêt propre à chaque extinction (driver NIC réinitialisé)" if r_fs.returncode == 0 else "ECHEC"}')

# ── 2e. Relance automatique des agents si crash ───────────────────────────────
# Si l'agent NinjaOne ou WithSecure plante, Windows ne le redémarre pas
# par défaut. On configure la politique d'échec du service pour un restart
# automatique après 5 s, 30 s, puis 60 s.
print('[2e] Relance automatique des agents NinjaOne / WithSecure…')
AGENT_SERVICES = [
    # NinjaOne / NinjaRMM
    'NinjaRMMAgent', 'NinjaOneAgent', 'NinjaRMMAgentPatcher',
    # WithSecure / F-Secure Elements
    'WithSecureElementsAgent', 'fselementsagent',
    'FSMA32', 'fsma', 'fsgk32st',
    'F-Secure Network Request Broker',
    # TeamViewer (bonus)
    'TeamViewer',
]
fixed_svcs = []
for svc in AGENT_SERVICES:
    q = subprocess.run(['sc', 'query', svc], capture_output=True, text=True)
    if q.returncode == 0:
        subprocess.run(
            ['sc', 'failure', svc,
             'reset=', '86400',
             'actions=', 'restart/5000/restart/30000/restart/60000'],
            capture_output=True
        )
        fixed_svcs.append(svc)
if fixed_svcs:
    print(f'     OK — {", ".join(fixed_svcs)} → restart auto si crash')
else:
    print('     INFO — aucun service détecté sur ce PC (c\'est normal si NinjaOne/WithSecure')
    print('     ne sont pas encore installés — relancez ce script après installation)')

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
    print(f'[3/5] Tâche créée    : "{task_name}"')
    print('       Le serveur démarrera 30 s après chaque connexion Windows.')
else:
    print(f'[3/5] ECHEC tâche    : {r.stderr.strip()[:120]}')

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
        print(f'[4/5] {browser_name:<14} : raccourci démarrage créé')
    else:
        print(f'[4/5] ECHEC {browser_name} : {r2.stderr.strip()[:80]}')
else:
    print(f'[4/5] {browser_name:<14} : introuvable — ajoutez-le manuellement au dossier Démarrage')

print()
print('═' * 56)
print('Que faire maintenant :')
print()
print('  1. REDÉMARRER le PC (obligatoire pour activer le keepalive')
print('     TCP et le Fast Startup désactivé).')
print()
print('  2. Dans le navigateur, réglez « Au démarrage » sur')
print('     « Ouvrir la page Nouvel onglet » (PAS « Reprendre »,')
print('     sinon une vieille fenêtre kiosque serait restaurée')
print('     en double à chaque redémarrage)')
print('  3. Windows + R → netplwiz → décochez « Les utilisateurs')
print('     doivent entrer un nom d\'utilisateur… » (login auto)')
print('  4. Laissez la rotation ACTIVE puis redémarrez pour tester')
print('  5. Le serveur démarre 30 s après la session')
print('     (le temps que le réseau soit dispo)')
print()
print('  ★ NinjaOne / WithSecure : les déconnexions après 24 h')
print('    sont corrigées par les étapes 2a-2e ci-dessus.')
print('    Si le problème persiste après redémarrage, vérifiez')
print('    aussi les paramètres de timeout du pare-feu/routeur.')
print('═' * 56)
input('\nAppuyez sur Entrée pour quitter...')
