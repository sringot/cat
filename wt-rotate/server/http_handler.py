import json
from aiohttp import web
from server import state, tls


async def handle_http(request):
    path = request.path.split('?')[0]

    # Certificat à installer sur le téléphone pour activer le micro vocal (HTTPS).
    # Type x-x509-ca-cert + pas de Content-Disposition : iOS propose alors
    # l'installation du profil au lieu d'enregistrer un fichier.
    if path in ('/cert.crt', '/cert.pem'):
        data = tls.cert_bytes()
        if data:
            return web.Response(body=data,
                                content_type='application/x-x509-ca-cert',
                                headers={'Cache-Control': 'no-store'})
        return web.Response(status=404, text='certificat indisponible')

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
