#!/usr/bin/env python3
"""
wt-rotate Remote Control Server
pip install websockets qrcode
"""
import asyncio, json, socket, threading, io
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

PORT_WS   = 8765
PORT_HTTP = 8766

local_ip    = "127.0.0.1"
ext_ws      = None
mob_clients = set()
state       = {}
qr_cache    = None   # Cached QR SVG bytes

# ── QR code generation ────────────────────────────────────────────────────────

def make_qr_svg(url):
    try:
        import qrcode
        import qrcode.image.svg
        factory = qrcode.image.svg.SvgPathImage
        img = qrcode.make(url, image_factory=factory, border=2)
        buf = io.BytesIO()
        img.save(buf)
        return buf.getvalue()
    except ImportError:
        return None
    except Exception:
        return None

# ── HTTP server ───────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/info':
            body = json.dumps({
                'ip': local_ip, 'ws_port': PORT_WS, 'http_port': PORT_HTTP
            }).encode()
            self._send(200, 'application/json', body,
                       extra=[('Access-Control-Allow-Origin', '*')])

        elif self.path.split('?')[0] == '/qr.svg':
            if qr_cache:
                self._send(200, 'image/svg+xml', qr_cache,
                           extra=[('Access-Control-Allow-Origin', '*'),
                                  ('Cache-Control', 'no-store')])
            else:
                self._send(503, 'text/plain', b'pip install qrcode')

        else:
            try:
                body = (Path(__file__).parent / 'control.html').read_bytes()
                self._send(200, 'text/html; charset=utf-8', body,
                           extra=[('Cache-Control', 'no-store')])
            except FileNotFoundError:
                self._send(404, 'text/plain', b'control.html introuvable')

    def _send(self, code, ct, body, extra=None):
        self.send_response(code)
        self.send_header('Content-Type', ct)
        for k, v in (extra or []):
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a): pass

def run_http():
    HTTPServer(('0.0.0.0', PORT_HTTP), Handler).serve_forever()

# ── WebSocket server ──────────────────────────────────────────────────────────

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
        await ws.send(json.dumps({
            'type': 'ack', 'ip': local_ip, 'http_port': PORT_HTTP
        }))
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

    control_url = f'http://{local_ip}:{PORT_HTTP}/'
    qr_cache = make_qr_svg(control_url)

    threading.Thread(target=run_http, daemon=True).start()

    print('╔══════════════════════════════════════════╗')
    print('║    wt-rotate Remote Control Server       ║')
    print('╠══════════════════════════════════════════╣')
    print(f'║  IP locale  : {local_ip:<27}║')
    print(f'║  URL mobile : {control_url:<27}║')
    qr_status = 'OK' if qr_cache else 'manquant (pip install qrcode)'
    print(f'║  QR code    : {qr_status:<27}║')
    print('╚══════════════════════════════════════════╝')
    print('\nEn attente de connexions...\n')

    import websockets
    async with websockets.serve(handle, '0.0.0.0', PORT_WS):
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
