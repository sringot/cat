#!/usr/bin/env python3
"""
wt-rotate Remote Control Server
pip install websockets
"""
import asyncio, json, random, socket, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

PORT_WS   = 8765   # WebSocket  (extension + mobile)
PORT_HTTP = 8766   # HTTP       (control page + /info)

PIN      = f"{random.randint(0, 9999):04d}"
local_ip = "127.0.0.1"

ext_ws = None   # Extension WebSocket
mob_ws = None   # Mobile   WebSocket
state  = {}     # Latest extension state

# ── HTTP server ───────────────────────────────────────────────────────────────

class HTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/info":
            body = json.dumps({
                "pin": PIN, "ip": local_ip,
                "ws_port": PORT_WS, "http_port": PORT_HTTP
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        else:
            try:
                html = (Path(__file__).parent / "control.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html)
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"control.html introuvable")

    def log_message(self, *a): pass

def run_http():
    HTTPServer(("0.0.0.0", PORT_HTTP), HTTPHandler).serve_forever()

# ── WebSocket server ──────────────────────────────────────────────────────────

async def handle(ws):
    global ext_ws, mob_ws, state

    try:
        raw = await asyncio.wait_for(ws.recv(), timeout=10)
        msg = json.loads(raw)
    except Exception:
        return

    client = msg.get("type")

    if client == "extension":
        ext_ws = ws
        print("[+] Extension connectée")
        await ws.send(json.dumps({
            "type": "ack", "pin": PIN,
            "ip": local_ip, "http_port": PORT_HTTP
        }))
        try:
            async for raw in ws:
                d = json.loads(raw)
                if d.get("type") == "state":
                    state = d
                    if mob_ws:
                        try: await mob_ws.send(raw)
                        except: pass
        except Exception:
            pass
        finally:
            ext_ws = None
            print("[-] Extension déconnectée")

    elif client == "mobile":
        if msg.get("pin") != PIN:
            await ws.send(json.dumps({"type": "error", "msg": "PIN invalide"}))
            return
        mob_ws = ws
        print("[+] Mobile connecté")
        await ws.send(json.dumps({"type": "auth_ok"}))
        if state:
            await ws.send(json.dumps({**state, "type": "state"}))
        try:
            async for raw in ws:
                d = json.loads(raw)
                if d.get("type") == "command" and ext_ws:
                    try: await ext_ws.send(raw)
                    except: pass
        except Exception:
            pass
        finally:
            mob_ws = None
            print("[-] Mobile déconnecté")

# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    global local_ip
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    threading.Thread(target=run_http, daemon=True).start()

    print("╔══════════════════════════════════════════╗")
    print("║    wt-rotate Remote Control Server       ║")
    print("╠══════════════════════════════════════════╣")
    print(f"║  IP locale  : {local_ip:<27}║")
    print(f"║  PIN        : {PIN:<27}║")
    print(f"║  URL mobile : http://{local_ip}:{PORT_HTTP}/{'':8}║")
    print("╚══════════════════════════════════════════╝")
    print("\nEn attente de connexions...\n")

    import websockets
    async with websockets.serve(handle, "0.0.0.0", PORT_WS):
        await asyncio.Future()

if __name__ == "__main__":
    try:
        import websockets
    except ImportError:
        print("ERREUR : pip install websockets")
        input("Appuyez sur Entrée pour quitter...")
        raise SystemExit(1)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServeur arrêté.")
