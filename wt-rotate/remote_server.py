#!/usr/bin/env python3
"""
wt-rotate Remote Control Server — HTTP + WebSocket sur le même port (8765)
pip install aiohttp qrcode
"""
import asyncio, json, socket, io
from pathlib import Path
from aiohttp import web, WSMsgType

PORT = 8765

local_ip    = '127.0.0.1'
ext_ws      = None
mob_clients = set()
state       = {}
qr_cache    = None
html_cache  = None

# ── QR code ───────────────────────────────────────────────────────────────────

def make_qr_svg(url):
    try:
        import qrcode, qrcode.image.svg
        buf = io.BytesIO()
        qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, border=2).save(buf)
        return buf.getvalue()
    except Exception:
        return None

# ── Gestionnaire principal (HTTP + WebSocket sur le même port) ────────────────

async def handle(request):
    if request.headers.get('upgrade', '').lower() == 'websocket':
        return await handle_ws(request)
    return await handle_http(request)

async def handle_http(request):
    path = request.path.split('?')[0]

    if path == '/info':
        body = json.dumps({'ip': local_ip, 'ws_port': PORT, 'http_port': PORT}).encode()
        return web.Response(body=body, content_type='application/json',
                            headers={'Access-Control-Allow-Origin': '*'})

    if path == '/qr.svg':
        if qr_cache:
            return web.Response(body=qr_cache, content_type='image/svg+xml',
                                headers={'Cache-Control': 'no-store',
                                         'Access-Control-Allow-Origin': '*'})
        return web.Response(status=503, text='pip install qrcode')

    if html_cache:
        return web.Response(body=html_cache,
                            headers={'Content-Type': 'text/html; charset=utf-8',
                                     'Cache-Control': 'no-store'})
    return web.Response(status=404, text='control.html introuvable')

async def handle_ws(request):
    global ext_ws, state
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    try:
        msg_data = await asyncio.wait_for(ws.receive(), timeout=10)
        if msg_data.type != WSMsgType.TEXT:
            return ws
        msg = json.loads(msg_data.data)
    except Exception:
        return ws

    if msg.get('type') == 'extension':
        ext_ws = ws
        print('[+] Extension connectée')
        await ws.send_str(json.dumps({'type': 'ack', 'ip': local_ip, 'http_port': PORT}))
        try:
            async for msg_data in ws:
                if msg_data.type == WSMsgType.TEXT:
                    d = json.loads(msg_data.data)
                    if d.get('type') == 'state':
                        state = d
                        dead = set()
                        for m in list(mob_clients):
                            try: await m.send_str(msg_data.data)
                            except: dead.add(m)
                        mob_clients -= dead
        except Exception:
            pass
        finally:
            ext_ws = None
            state = {}
            print('[-] Extension déconnectée')

    elif msg.get('type') == 'mobile':
        mob_clients.add(ws)
        print(f'[+] Mobile connecté ({len(mob_clients)} actif(s))')
        await ws.send_str(json.dumps({'type': 'auth_ok'}))
        if state:
            await ws.send_str(json.dumps({**state, 'type': 'state'}))
        try:
            async for msg_data in ws:
                if msg_data.type == WSMsgType.TEXT:
                    d = json.loads(msg_data.data)
                    if d.get('type') == 'command' and ext_ws:
                        try: await ext_ws.send_str(msg_data.data)
                        except: pass
        except Exception:
            pass
        finally:
            mob_clients.discard(ws)
            print(f'[-] Mobile déconnecté ({len(mob_clients)} actif(s))')

    return ws

# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    global local_ip, qr_cache, html_cache

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    control_url = f'http://{local_ip}:{PORT}/'
    qr_cache    = make_qr_svg(control_url)

    try:
        html_cache = (Path(__file__).parent / 'control.html').read_bytes()
    except Exception:
        html_cache = b'<h1>control.html introuvable</h1>'

    print('╔══════════════════════════════════════════╗')
    print('║    wt-rotate Remote Control Server       ║')
    print('╠══════════════════════════════════════════╣')
    print(f'║  IP locale  : {local_ip:<27}║')
    print(f'║  URL mobile : {control_url:<27}║')
    print(f'║  QR code    : {"OK" if qr_cache else "manquant (pip install qrcode)":<27}║')
    print('╚══════════════════════════════════════════╝')
    print('\nEn attente de connexions...\n')

    app = web.Application()
    app.router.add_route('*', '/',              handle)
    app.router.add_route('*', '/{path_info:.*}', handle)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    await asyncio.Future()

if __name__ == '__main__':
    try:
        from aiohttp import web, WSMsgType
    except ImportError:
        print('ERREUR : pip install aiohttp qrcode')
        input('Appuyez sur Entrée pour quitter...')
        raise SystemExit(1)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\nServeur arrêté.')
