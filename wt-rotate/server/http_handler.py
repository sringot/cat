import json
from pathlib import Path
from aiohttp import web
from server import state


async def handle_http(request):
    path = request.path.split('?')[0]

    if path == '/app.webmanifest':
        if state.manifest_cache:
            return web.Response(body=state.manifest_cache,
                                content_type='application/manifest+json',
                                headers={'Cache-Control': 'no-store',
                                         'Access-Control-Allow-Origin': '*'})
        return web.Response(status=404)

    if path.startswith('/icons/'):
        data = state.icon_cache.get(path)
        if data:
            return web.Response(body=data, content_type='image/png',
                                headers={'Cache-Control': 'max-age=86400'})
        return web.Response(status=404)

    if path == '/sw.js':
        base = Path(__file__).parent.parent
        sw = base / 'sw.js'
        if sw.exists():
            return web.Response(body=sw.read_bytes(),
                                content_type='application/javascript',
                                headers={'Cache-Control': 'no-store',
                                         'Service-Worker-Allowed': '/'})
        return web.Response(status=404)

    if path == '/docs':
        base = Path(__file__).parent.parent
        docs = base / 'docs.html'
        if docs.exists():
            return web.Response(body=docs.read_bytes(),
                                headers={'Content-Type': 'text/html; charset=utf-8',
                                         'Cache-Control': 'no-store'})
        return web.Response(status=404, text='docs.html introuvable')

    if path == '/info':
        body = json.dumps({'ip': state.local_ip,
                           'ws_port': state.PORT,
                           'http_port': state.PORT}).encode()
        return web.Response(body=body, content_type='application/json',
                            headers={'Access-Control-Allow-Origin': '*'})

    if path == '/qr.svg':
        if state.qr_cache:
            # Pas de CORS '*' ici : le QR encode l'URL + token. L'extension le lit
            # en local (host_permissions <all_urls> → non soumise au CORS) ; une
            # page web tierce ne doit pas pouvoir fetch le SVG pour en extraire le
            # token et prendre la main sur le kiosque.
            return web.Response(body=state.qr_cache, content_type='image/svg+xml',
                                headers={'Cache-Control': 'no-store'})
        return web.Response(status=503, text='pip install qrcode')

    # /app → la télécommande ; / (cible du QR code) → le guide d'installation
    if path == '/app' and state.html_cache:
        return web.Response(body=state.html_cache,
                            headers={'Content-Type': 'text/html; charset=utf-8',
                                     'Cache-Control': 'no-store'})

    if state.guide_cache:
        return web.Response(body=state.guide_cache,
                            headers={'Content-Type': 'text/html; charset=utf-8',
                                     'Cache-Control': 'no-store'})
    if state.html_cache:  # guide.html manquant : on sert la télécommande direct
        return web.Response(body=state.html_cache,
                            headers={'Content-Type': 'text/html; charset=utf-8',
                                     'Cache-Control': 'no-store'})
    return web.Response(status=404, text='control.html introuvable')
