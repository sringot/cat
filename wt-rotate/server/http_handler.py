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

    if path == '/push-pubkey':
        from server import push as _push
        if _push.VAPID_AVAILABLE:
            return web.Response(body=json.dumps({'publicKey': _push.VAPID_PUBLIC}).encode(),
                                content_type='application/json',
                                headers={'Access-Control-Allow-Origin': '*'})
        return web.Response(status=503, text='pywebpush not installed')

    if path == '/push-subscribe':
        if request.method in ('POST', 'OPTIONS'):
            if request.method == 'OPTIONS':
                return web.Response(headers={'Access-Control-Allow-Origin': '*',
                                             'Access-Control-Allow-Methods': 'POST',
                                             'Access-Control-Allow-Headers': 'Content-Type'})
            try:
                sub = await request.json()
                from server import push as _push
                _push.save_subscription(sub)
                return web.Response(body=b'{"ok":true}', content_type='application/json',
                                    headers={'Access-Control-Allow-Origin': '*'})
            except Exception as e:
                return web.Response(status=400, text=str(e))

    if path == '/info':
        body = json.dumps({'ip': state.local_ip,
                           'ws_port': state.PORT,
                           'http_port': state.PORT}).encode()
        return web.Response(body=body, content_type='application/json',
                            headers={'Access-Control-Allow-Origin': '*'})

    if path == '/qr.svg':
        if state.qr_cache:
            return web.Response(body=state.qr_cache, content_type='image/svg+xml',
                                headers={'Cache-Control': 'no-store',
                                         'Access-Control-Allow-Origin': '*'})
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
