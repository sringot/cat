#!/usr/bin/env python3
"""
wt-rotate Remote Control Server — HTTP + WebSocket on a single port (8765)
pip install websockets qrcode
"""
import asyncio, json, socket, io, http
from pathlib import Path

PORT = 8765   # Single port: HTTP GET → serves page/QR, WebSocket upgrade → relay

local_ip    = "127.0.0.1"
ext_ws      = None
mob_clients = set()
state       = {}
qr_cache    = None

# ── QR code ───────────────────────────────────────────────────────────────────

def make_qr_svg(url):
    try:
        import qrcode, qrcode.image.svg
        buf = io.BytesIO()
        qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, border=2).save(buf)
        return buf.getvalue()
    except Exception:
        return None

# ── HTTP responses (shared by both API flavours) ──────────────────────────────

def _http(path):
    """Return (status, [(header, value)], body) for an HTTP request."""
    clean = path.split('?')[0]
    if clean == '/info':
        body = json.dumps({'ip': local_ip, 'ws_port': PORT, 'http_port': PORT}).encode()
        return http.HTTPStatus.OK, [
            ('Content-Type', 'application/json'),
            ('Access-Control-Allow-Origin', '*'),
        ], body
    if clean == '/qr.svg':
        if qr_cache:
            return http.HTTPStatus.OK, [
                ('Content-Type', 'image/svg+xml'),
                ('Access-Control-Allow-Origin', '*'),
                ('Cache-Control', 'no-store'),
            ], qr_cache
        return http.HTTPStatus.SERVICE_UNAVAILABLE, [], b'pip install qrcode'
    try:
        body = (Path(__file__).parent / 'control.html').read_bytes()
        return http.HTTPStatus.OK, [
            ('Content-Type', 'text/html; charset=utf-8'),
            ('Cache-Control', 'no-store'),
        ], body
    except FileNotFoundError:
        return http.HTTPStatus.NOT_FOUND, [], b'control.html introuvable'

# ── process_request — compatible websockets 10-11 (legacy) AND 12+ (new) ─────
#
# websockets < 12  : process_request(path: str, headers: Headers)
#                    → (HTTPStatus, [(k,v)], bytes) | None
# websockets ≥ 12  : process_request(connection, request)
#                    → Response | None
#
# We detect which API is available at import time and define accordingly.

try:
    from websockets.http11 import Response as _WsResponse          # websockets ≥ 12
    from websockets.datastructures import Headers as _WsHeaders

    async def process_request(connection, request):
        if 'websocket' in request.headers.get('upgrade', '').lower():
            return None   # Let the WebSocket handshake proceed
        status, hdrs, body = _http(request.path)
        ws_hdrs = _WsHeaders(hdrs + [('Content-Length', str(len(body)))])
        return _WsResponse(status.value, status.phrase, ws_hdrs, body)

except ImportError:
    # Legacy API (websockets 10 / 11)
    async def process_request(path, request_headers):               # type: ignore[misc]
        if 'websocket' in request_headers.get('upgrade', '').lower():
            return None
        return _http(path)

# ── WebSocket handler ─────────────────────────────────────────────────────────

async def handle(ws):
    global ext_ws, mob_clients, state
    try:
        raw = await asyncio.wait_for(ws.recv(), timeout=10)
        msg = json.loads(raw)
    except Exception:
        return

    if msg.get('type') == 'extension':
        ext_ws = ws
        print('[+] Extension connectée')
        await ws.send(json.dumps({'type': 'ack', 'ip': local_ip, 'http_port': PORT}))
        try:
            async for raw in ws:
                d = json.loads(raw)
                if d.get('type') == 'state':
                    state = d
                    dead = set()
                    for m in mob_clients:
                        try: await m.send(raw)
                        except: dead.add(m)
                    mob_clients -= dead
        except Exception:
            pass
        finally:
            ext_ws = None
            print('[-] Extension déconnectée')

    elif msg.get('type') == 'mobile':
        mob_clients.add(ws)
        print(f'[+] Mobile connecté ({len(mob_clients)} actif(s))')
        await ws.send(json.dumps({'type': 'auth_ok'}))
        if state:
            await ws.send(json.dumps({**state, 'type': 'state'}))
        try:
            async for raw in ws:
                d = json.loads(raw)
                if d.get('type') == 'command' and ext_ws:
                    try: await ext_ws.send(raw)
                    except: pass
        except Exception:
            pass
        finally:
            mob_clients.discard(ws)
            print(f'[-] Mobile déconnecté ({len(mob_clients)} actif(s))')

# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    global local_ip, qr_cache
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    control_url = f'http://{local_ip}:{PORT}/'
    qr_cache    = make_qr_svg(control_url)

    print('╔══════════════════════════════════════════╗')
    print('║    wt-rotate Remote Control Server       ║')
    print('╠══════════════════════════════════════════╣')
    print(f'║  IP locale  : {local_ip:<27}║')
    print(f'║  URL mobile : {control_url:<27}║')
    print(f'║  QR code    : {"OK" if qr_cache else "manquant (pip install qrcode)":<27}║')
    print('╚══════════════════════════════════════════╝')
    print('\nEn attente de connexions...\n')

    import websockets
    async with websockets.serve(handle, '0.0.0.0', PORT,
                                process_request=process_request):
        await asyncio.Future()

if __name__ == '__main__':
    try:
        import websockets
    except ImportError:
        print('ERREUR : pip install websockets qrcode')
        input('Appuyez sur Entrée pour quitter...')
        raise SystemExit(1)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\nServeur arrêté.')
