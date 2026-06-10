#!/usr/bin/env python3
"""
wt-rotate Remote Control Server
pip install aiohttp qrcode
"""
import asyncio
import io
import socket
from pathlib import Path


async def main():
    from aiohttp import web
    from server import state, auth
    from server.http_handler import handle_http
    from server.ws_handler import handle_ws, keepalive_loop

    # Detect LAN IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        state.local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    # QR code encodes URL with auth token so rescanning is only needed after token rotation
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
        import json as _json
        manifest = _json.loads((base / 'app.webmanifest').read_bytes())
        manifest['start_url'] = f'/?token={auth.TOKEN}'
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
    print('╔══════════════════════════════════════════╗')
    print('║    wt-rotate Remote Control Server       ║')
    print('╠══════════════════════════════════════════╣')
    print(f'║  IP locale  : {state.local_ip:<27}║')
    print(f'║  URL mobile : {plain_url:<27}║')
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

    asyncio.create_task(keepalive_loop())
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
