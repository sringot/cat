#!/usr/bin/env python3
"""
wt-rotate Remote Control Server
pip install aiohttp qrcode
"""
import asyncio, json, socket, io, time
import xml.etree.ElementTree as ET
from pathlib import Path

PORT = 8765

local_ip       = '127.0.0.1'
ext_ws         = None
mob_clients    = set()
state          = {}
qr_cache       = None
html_cache     = None
manifest_cache = None
icon_cache     = {}

_feed_cache      = None
_feed_cache_time = 0
FEED_CACHE_SECONDS = 300
CHANNELS_FILE = Path(__file__).parent / 'feed_channels.json'
NS_ATOM = 'http://www.w3.org/2005/Atom'
NS_YT   = 'http://www.youtube.com/xml/schemas/2015'

# ── QR code ───────────────────────────────────────────────────────────────────

def make_qr_svg(url):
    try:
        import qrcode, qrcode.image.svg
        buf = io.BytesIO()
        qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, border=2).save(buf)
        return buf.getvalue()
    except Exception:
        return None

# ── Channel persistence ───────────────────────────────────────────────────────

def load_channels():
    try:
        return json.loads(CHANNELS_FILE.read_text(encoding='utf-8'))
    except:
        return []

def save_channels(channels):
    try:
        CHANNELS_FILE.write_text(json.dumps(channels, ensure_ascii=False, indent=2), encoding='utf-8')
    except:
        pass

# ── YouTube feed ──────────────────────────────────────────────────────────────

async def fetch_channel_feed(session, channel_id):
    url = f'https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}'
    try:
        import aiohttp
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                return []
            text = await resp.text()
    except:
        return []
    try:
        root = ET.fromstring(text)
        author_el = root.find(f'{{{NS_ATOM}}}author/{{{NS_ATOM}}}name')
        channel_name = author_el.text if author_el is not None else channel_id
        items = []
        for entry in root.findall(f'{{{NS_ATOM}}}entry'):
            try:
                title_el  = entry.find(f'{{{NS_ATOM}}}title')
                pub_el    = entry.find(f'{{{NS_ATOM}}}published')
                vid_id_el = entry.find(f'{{{NS_YT}}}videoId')
                link_el   = entry.find(f'{{{NS_ATOM}}}link[@rel="alternate"]')
                vid_id = vid_id_el.text if vid_id_el is not None else ''
                if not vid_id:
                    continue
                items.append({
                    'id':        vid_id,
                    'title':     (title_el.text if title_el is not None else ''),
                    'channel':   channel_name,
                    'published': (pub_el.text   if pub_el  is not None else ''),
                    'url':       (link_el.get('href', '') if link_el is not None
                                  else f'https://www.youtube.com/watch?v={vid_id}'),
                    'thumbnail': f'https://img.youtube.com/vi/{vid_id}/hqdefault.jpg',
                })
            except:
                continue
        return items
    except:
        return []

async def get_feed():
    global _feed_cache, _feed_cache_time
    now = time.time()
    if _feed_cache is not None and (now - _feed_cache_time) < FEED_CACHE_SECONDS:
        return _feed_cache
    channels = load_channels()
    if not channels:
        _feed_cache = []
        _feed_cache_time = now
        return _feed_cache
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            results = await asyncio.gather(
                *[fetch_channel_feed(session, ch['id']) for ch in channels],
                return_exceptions=True
            )
    except:
        return _feed_cache or []
    all_items = [item for r in results if isinstance(r, list) for item in r]
    all_items.sort(key=lambda x: x.get('published', ''), reverse=True)
    _feed_cache = all_items
    _feed_cache_time = now
    return _feed_cache

def invalidate_feed_cache():
    global _feed_cache, _feed_cache_time
    _feed_cache = None
    _feed_cache_time = 0

# ── HTTP ──────────────────────────────────────────────────────────────────────

async def handle_http(request):
    from aiohttp import web
    path = request.path.split('?')[0]

    if path == '/app.webmanifest':
        if manifest_cache:
            return web.Response(body=manifest_cache, content_type='application/manifest+json',
                                headers={'Cache-Control': 'no-store',
                                         'Access-Control-Allow-Origin': '*'})
        return web.Response(status=404)

    if path.startswith('/icons/'):
        data = icon_cache.get(path)
        if data:
            return web.Response(body=data, content_type='image/png',
                                headers={'Cache-Control': 'max-age=86400'})
        return web.Response(status=404)

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

    # ── Feed endpoints ────────────────────────────────────────────────────────

    if path == '/feed':
        try:
            items = await get_feed()
        except:
            items = []
        return web.Response(
            body=json.dumps(items, ensure_ascii=False).encode(),
            content_type='application/json',
            headers={'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store'}
        )

    if path == '/feed/channels':
        if request.method == 'POST':
            try:
                body = await request.json()
                ch_id = (body.get('id') or '').strip()
                if not ch_id:
                    return web.Response(status=400, text='Missing id')
                channels = load_channels()
                if not any(c['id'] == ch_id for c in channels):
                    channels.append({'id': ch_id, 'name': (body.get('name') or ch_id).strip()})
                    save_channels(channels)
                    invalidate_feed_cache()
                return web.Response(
                    body=json.dumps(channels, ensure_ascii=False).encode(),
                    content_type='application/json',
                    headers={'Access-Control-Allow-Origin': '*'}
                )
            except Exception as e:
                return web.Response(status=400, text=str(e))
        # GET
        channels = load_channels()
        return web.Response(
            body=json.dumps(channels, ensure_ascii=False).encode(),
            content_type='application/json',
            headers={'Access-Control-Allow-Origin': '*'}
        )

    if path.startswith('/feed/channels/') and request.method == 'DELETE':
        ch_id = path[len('/feed/channels/'):]
        channels = [c for c in load_channels() if c['id'] != ch_id]
        save_channels(channels)
        invalidate_feed_cache()
        return web.Response(
            body=json.dumps(channels, ensure_ascii=False).encode(),
            content_type='application/json',
            headers={'Access-Control-Allow-Origin': '*'}
        )

    # ── OPTIONS preflight ─────────────────────────────────────────────────────

    if request.method == 'OPTIONS':
        return web.Response(
            status=204,
            headers={
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
            }
        )

    if html_cache:
        return web.Response(body=html_cache,
                            headers={'Content-Type': 'text/html; charset=utf-8',
                                     'Cache-Control': 'no-store'})
    return web.Response(status=404, text='control.html introuvable')

# ── Keepalive (application-level pings) ───────────────────────────────────────
# Protocol-level heartbeat pings are silently handled by the browser and do NOT
# fire JS onmessage — so they never reset Chrome's 30s service-worker idle timer.
# JSON pings DO fire onmessage, keeping the extension SW alive.

async def keepalive_loop():
    ping = json.dumps({'type': 'ping'})
    while True:
        await asyncio.sleep(20)
        if ext_ws and not ext_ws.closed:
            try: await ext_ws.send_str(ping)
            except: pass
        dead = set()
        for m in list(mob_clients):
            if m.closed: dead.add(m); continue
            try: await m.send_str(ping)
            except: dead.add(m)
        mob_clients -= dead

# ── WebSocket ─────────────────────────────────────────────────────────────────

async def handle_ws(request):
    global ext_ws, state, mob_clients
    from aiohttp import web, WSMsgType

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
        ext_on = json.dumps({'type': 'ext_status', 'connected': True})
        dead = set()
        for m in list(mob_clients):
            try: await m.send_str(ext_on)
            except: dead.add(m)
        mob_clients -= dead
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
                    # pong responses from extension are silently ignored
        except Exception:
            pass
        finally:
            if ext_ws is ws:
                ext_ws = None
            print('[-] Extension déconnectée')
            ext_off = json.dumps({'type': 'ext_status', 'connected': False})
            dead = set()
            for m in list(mob_clients):
                try: await m.send_str(ext_off)
                except: dead.add(m)
            mob_clients -= dead

    elif msg.get('type') == 'mobile':
        mob_clients.add(ws)
        print(f'[+] Mobile connecté ({len(mob_clients)} actif(s))')
        await ws.send_str(json.dumps({'type': 'auth_ok'}))
        await ws.send_str(json.dumps({'type': 'ext_status', 'connected': ext_ws is not None and not ext_ws.closed}))
        if state:
            await ws.send_str(json.dumps({**state, 'type': 'state'}))
        try:
            async for msg_data in ws:
                if msg_data.type == WSMsgType.TEXT:
                    d = json.loads(msg_data.data)
                    if d.get('type') == 'command':
                        if ext_ws and not ext_ws.closed:
                            try: await ext_ws.send_str(msg_data.data)
                            except: pass
                        else:
                            try: await ws.send_str(json.dumps({'type': 'cmd_error', 'code': 'ext_offline'}))
                            except: pass
                    # pong responses from mobile are silently ignored
        except Exception:
            pass
        finally:
            mob_clients.discard(ws)
            print(f'[-] Mobile déconnecté ({len(mob_clients)} actif(s))')

    return ws

# ── Routeur principal ─────────────────────────────────────────────────────────

async def handle(request):
    if request.headers.get('Upgrade', '').lower() == 'websocket':
        return await handle_ws(request)
    return await handle_http(request)

# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    global local_ip, qr_cache, html_cache, manifest_cache, icon_cache
    from aiohttp import web

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

    try:
        manifest_cache = (Path(__file__).parent / 'app.webmanifest').read_bytes()
    except Exception:
        pass

    icons_dir = Path(__file__).parent / 'icons'
    if icons_dir.exists():
        for icon_file in icons_dir.glob('*.png'):
            try:
                icon_cache[f'/icons/{icon_file.name}'] = icon_file.read_bytes()
            except Exception:
                pass

    if not CHANNELS_FILE.exists():
        save_channels([])

    print('╔══════════════════════════════════════════╗')
    print('║    wt-rotate Remote Control Server       ║')
    print('╠══════════════════════════════════════════╣')
    print(f'║  IP locale  : {local_ip:<27}║')
    print(f'║  URL mobile : {control_url:<27}║')
    print(f'║  QR code    : {"OK" if qr_cache else "manquant (pip install qrcode)":<27}║')
    print('╚══════════════════════════════════════════╝')
    print('\nEn attente de connexions...\n')

    app = web.Application()
    app.router.add_route('*', '/', handle)
    app.router.add_route('*', '/{path:.+}', handle)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()

    asyncio.create_task(keepalive_loop())
    await asyncio.Future()

if __name__ == '__main__':
    try:
        import aiohttp
    except ImportError:
        print('ERREUR : pip install aiohttp qrcode')
        input('Appuyez sur Entrée pour quitter...')
        raise SystemExit(1)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\nServeur arrêté.')
