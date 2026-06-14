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
    from server import state, auth, backup, library, ai_agent, stt, tls
    from server.http_handler import handle_http
    from server.ws_handler import handle_ws, keepalive_loop

    backup.load()   # playlist auto-sauvegardée lors d'une session précédente
    library.load()  # bibliothèque de playlists nommées
    ai_agent.init() # assistant vocal IA (optionnel — nécessite ANTHROPIC_API_KEY)
    stt.init()      # transcription vocale au micro (optionnel — nécessite GROQ_API_KEY)

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

    app = web.Application()
    app.router.add_get('/', handle)
    app.router.add_get('/{path:.+}', handle)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', state.PORT)
    await site.start()

    # Serveur HTTPS (port 8766) : indispensable pour le micro vocal sur
    # téléphone (getUserMedia exige un contexte sécurisé). Certificat auto-signé.
    ssl_ctx = tls.ssl_context() if tls.ensure_cert(state.local_ip) else None
    if ssl_ctx:
        try:
            https_site = web.TCPSite(runner, '0.0.0.0', state.HTTPS_PORT, ssl_context=ssl_ctx)
            await https_site.start()
            state.https_on = True
        except Exception as e:
            print(f'[!] HTTPS non démarré : {e}')

    plain_url = f'http://{state.local_ip}:{state.PORT}/'
    sec_url   = f'https://{state.local_ip}:{state.HTTPS_PORT}/'
    print('╔══════════════════════════════════════════╗')
    print('║    wt-rotate Remote Control Server       ║')
    print('╠══════════════════════════════════════════╣')
    print(f'║  IP locale  : {state.local_ip:<27}║')
    print(f'║  URL mobile : {plain_url:<27}║')
    print(f'║  Token auth : {auth.TOKEN:<27}║')
    print(f'║  QR code    : {"OK" if state.qr_cache else "manquant (pip install qrcode)":<27}║')
    ai_txt = "OK" if ai_agent.is_available() else "non config. (cle_ia.txt)"
    print(f'║  IA vocale  : {ai_txt:<27}║')
    mic_txt = "OK" if stt.is_available() else "non config. (cle_groq.txt)"
    print(f'║  Micro voc. : {mic_txt:<27}║')
    https_txt = sec_url if state.https_on else "off (lib cryptography)"
    print(f'║  HTTPS micro: {https_txt:<27}║')
    print('╚══════════════════════════════════════════╝')
    print('\nEn attente de connexions...\n')

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
