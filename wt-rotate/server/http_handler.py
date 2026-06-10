import json
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

    if state.html_cache:
        return web.Response(body=state.html_cache,
                            headers={'Content-Type': 'text/html; charset=utf-8',
                                     'Cache-Control': 'no-store'})
    return web.Response(status=404, text='control.html introuvable')
