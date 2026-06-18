#!/usr/bin/env python3
"""
wt-rotate Remote Control Server
pip install aiohttp qrcode
"""
import asyncio
import io
import logging
import socket
from pathlib import Path


async def main():
    from aiohttp import web
    from server import state, auth, backup, library
    from server.http_handler import handle_http
    from server.ws_handler import handle_ws, keepalive_loop

    # Journalisation : événements runtime horodatés (le bandeau reste en print)
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s  %(levelname)-7s %(message)s',
                        datefmt='%H:%M:%S')
    # aiohttp loguerait chaque requête HTTP (screenshots, assets…) en INFO —
    # c'est du bruit continu ; on garde uniquement les warnings aiohttp.
    logging.getLogger('aiohttp.access').setLevel(logging.WARNING)
    logging.getLogger('aiohttp.server').setLevel(logging.WARNING)

    backup.load()   # playlist auto-sauvegardée lors d'une session précédente
    library.load()  # bibliothèque de playlists nommées

    # Detect LAN IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        state.local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    # QR code always uses the raw LAN IP — hostname.local requires mDNS which
    # Android Chrome does not support reliably, causing QR scans to fail.
    control_url = f'http://{state.local_ip}:{state.PORT}/?token={auth.TOKEN}'
    try:
        import qrcode
        import qrcode.image.svg
        buf = io.BytesIO()
        qrcode.make(control_url, image_factory=qrcode.image.svg.SvgPathImage, border=2).save(buf)
        state.qr_cache = buf.getvalue()
    except Exception:
        state.qr_cache = None

    # Load static assets
    base = Path(__file__).parent
    try:
        state.html_cache = (base / 'control.html').read_bytes()
    except Exception:
        state.html_cache = b'<h1>control.html introuvable</h1>'
    try:
        state.guide_cache = (base / 'guide.html').read_bytes()
    except Exception:
        state.guide_cache = None
    try:
        import json as _json
        manifest = _json.loads((base / 'app.webmanifest').read_bytes())
        # L'app installée ouvre directement la télécommande, pas le guide
        manifest['start_url'] = f'/app?token={auth.TOKEN}'
        state.manifest_cache = _json.dumps(manifest).encode()
    except Exception:
        pass
    icons_dir = base / 'icons'
    if icons_dir.exists():
        for icon_file in icons_dir.glob('*.png'):
            try:
                state.icon_cache[f'/icons/{icon_file.name}'] = icon_file.read_bytes()
            except Exception:
                pass

    async def handle(request):
        if request.headers.get('Upgrade', '').lower() == 'websocket':
            return await handle_ws(request)
        return await handle_http(request)

    plain_url = f'http://{state.local_ip}:{state.PORT}/'
    try:
        _hn = socket.gethostname()
        hostname_url = f'http://{_hn}.local:{state.PORT}/'
    except Exception:
        hostname_url = plain_url
    print('╔══════════════════════════════════════════╗')
    print('║    wt-rotate Remote Control Server       ║')
    print('╠══════════════════════════════════════════╣')
    print(f'║  IP locale  : {state.local_ip:<27}║')
    print(f'║  Hostname   : {hostname_url:<27}║')
    print(f'║  Token auth : {auth.TOKEN:<27}║')
    print(f'║  QR code    : {"OK" if state.qr_cache else "manquant (pip install qrcode)":<27}║')
    print('╚══════════════════════════════════════════╝')
    print('\nEn attente de connexions...\n')

    app = web.Application()
    app.router.add_get('/', handle)
    app.router.add_get('/{path:.+}', handle)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', state.PORT)
    await site.start()

    # Référence forte conservée sur l'état : empêche le GC de la tâche et
    # la rend inspectable (la boucle est par ailleurs résiliente aux erreurs).
    state.keepalive_task = asyncio.create_task(keepalive_loop())
    await asyncio.Future()


if __name__ == '__main__':
    try:
        import aiohttp  # noqa: F401
    except ImportError:
        print('ERREUR : pip install aiohttp qrcode')
        input('Appuyez sur Entrée pour quitter...')
        raise SystemExit(1)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\nServeur arrêté.')
