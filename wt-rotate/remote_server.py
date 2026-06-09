#!/usr/bin/env python3
# FILE: /home/user/cat/wt-rotate/remote_server.py
"""
wt-rotate Remote Control Server  —  multi-TV edition
pip install aiohttp qrcode
"""
import asyncio, json, socket, io, time
import xml.etree.ElementTree as ET
from pathlib import Path

PORT = 8765

local_ip       = '127.0.0.1'
mob_clients    = set()
qr_cache       = None
html_cache     = None
manifest_cache = None
icon_cache     = {}

# ext_clients: tv_id -> { 'ws': ws|None, 'name': str, 'state': dict }
ext_clients = {}

# mob_tv_sel: id(ws) -> tv_id | None
mob_tv_sel = {}

# YouTube feed cache
_feed_cache        = None
_feed_cache_time   = 0
FEED_CACHE_SECONDS = 300

CHANNELS_FILE = Path(__file__).parent / 'feed_channels.json'

# ── Channel persistence ───────────────────────────────────────────────────────

def load_channels():
    try:
        return json.loads(CHANNELS_FILE.read_text(encoding='utf-8'))
    except Exception:
        return []

def save_channels(channels):
    try:
        CHANNELS_FILE.write_text(json.dumps(channels, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass

# ── QR code ───────────────────────────────────────────────────────────────────

def make_qr_svg(url):
    try:
        import qrcode, qrcode.image.svg
        buf = io.BytesIO()
        qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, border=2).save(buf)
        return buf.getvalue()
    except Exception:
        return None

# ── TV state helpers ──────────────────────────────────────────────────────────

def tv_snapshot():
    """Return list of {id, name, connected, state} for all known TVs."""
    result = []
    for tv_id, info in ext_clients.items():
        ws = info.get('ws')
        result.append({
            'id':        tv_id,
            'name':      info.get('name', tv_id),
            'connected': ws is not None and not ws.closed,
            'state':     info.get('state', {}),
        })
    return result

async def broadcast_tv_list():
    """Send tv_list to all connected mobiles."""
    msg = json.dumps({'type': 'tv_list', 'tvs': tv_snapshot()})
    dead = set()
    for m in list(mob_clients):
        if m.closed:
            dead.add(m)
            continue
        try:
            await m.send_str(msg)
        except Exception:
            dead.add(m)
    mob_clients -= dead

async def notify_watching(tv_id, payload_str):
    """Send a message only to mobiles currently watching a specific TV."""
    dead = set()
    for m in list(mob_clients):
        if mob_tv_sel.get(id(m)) != tv_id:
            continue
        if m.closed:
            dead.add(m)
            continue
        try:
            await m.send_str(payload_str)
        except Exception:
            dead.add(m)
    mob_clients -= dead

# ── YouTube RSS feed ──────────────────────────────────────────────────────────

NS_ATOM  = 'http://www.w3.org/2005/Atom'
NS_YT    = 'http://www.youtube.com/xml/schemas/2015'
NS_MEDIA = 'http://search.yahoo.com/mrss/'

async def fetch_channel_feed(session, channel_id):
    url = f'https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}'
    try:
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=8)
        async with session.get(url, timeout=timeout) as resp:
            if resp.status != 200:
                return []
            text = await resp.text()
    except Exception:
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

                title     = title_el.text  if title_el   is not None else ''
                published = pub_el.text    if pub_el     is not None else ''
                vid_id    = vid_id_el.text if vid_id_el  is not None else ''
                link_url  = link_el.get('href', '') if link_el is not None else ''

                if not vid_id:
                    continue

                thumbnail = f'https://img.youtube.com/vi/{vid_id}/hqdefault.jpg'
                yt_url    = f'https://www.youtube.com/watch?v={vid_id}'

                items.append({
                    'id':        vid_id,
                    'title':     title,
                    'channel':   channel_name,
                    'published': published,
                    'url':       link_url or yt_url,
                    'thumbnail': thumbnail,
                })
            except Exception:
                continue
        return items
    except Exception:
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
            tasks = [fetch_channel_feed(session, ch['id']) for ch in channels]
            results = await asyncio.gather(*tasks, return_exceptions=True)
    except Exception:
        return _feed_cache or []

    all_items = []
    for r in results:
        if isinstance(r, list):
            all_items.extend(r)

    # Sort by published descending
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

    # ── Feed endpoints ─────────────────────────────────────────────────────────
    if path == '/feed':
        try:
            items = await get_feed()
        except Exception:
            items = []
        return web.Response(
            body=json.dumps(items, ensure_ascii=False).encode(),
            content_type='application/json',
            headers={'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store'},
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
                    headers={'Access-Control-Allow-Origin': '*'},
                )
            except Exception as e:
                return web.Response(status=400, text=str(e))
        # GET
        channels = load_channels()
        return web.Response(
            body=json.dumps(channels, ensure_ascii=False).encode(),
            content_type='application/json',
            headers={'Access-Control-Allow-Origin': '*'},
        )

    # /feed/channels/{id}  DELETE
    if path.startswith('/feed/channels/') and request.method == 'DELETE':
        ch_id = path[len('/feed/channels/'):]
        channels = load_channels()
        channels = [c for c in channels if c['id'] != ch_id]
        save_channels(channels)
        invalidate_feed_cache()
        return web.Response(
            body=json.dumps(channels, ensure_ascii=False).encode(),
            content_type='application/json',
            headers={'Access-Control-Allow-Origin': '*'},
        )

    # ── OPTIONS preflight ──────────────────────────────────────────────────────
    if request.method == 'OPTIONS':
        return web.Response(
            status=204,
            headers={
                'Access-Control-Allow-Origin':  '*',
                'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
            },
        )

    # ── Static / existing endpoints ────────────────────────────────────────────
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

    if html_cache:
        return web.Response(body=html_cache,
                            headers={'Content-Type': 'text/html; charset=utf-8',
                                     'Cache-Control': 'no-store'})
    return web.Response(status=404, text='control.html introuvable')

# ── Keepalive ─────────────────────────────────────────────────────────────────

async def keepalive_loop():
    ping = json.dumps({'type': 'ping'})
    while True:
        await asyncio.sleep(20)
        # Ping all extension clients
        for tv_id, info in list(ext_clients.items()):
            ws = info.get('ws')
            if ws and not ws.closed:
                try:
                    await ws.send_str(ping)
                except Exception:
                    pass
        # Ping all mobile clients
        dead = set()
        for m in list(mob_clients):
            if m.closed:
                dead.add(m)
                continue
            try:
                await m.send_str(ping)
            except Exception:
                dead.add(m)
        mob_clients -= dead

# ── WebSocket ─────────────────────────────────────────────────────────────────

async def handle_ws(request):
    global mob_clients, ext_clients, mob_tv_sel
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

    # ── Extension client ───────────────────────────────────────────────────────
    if msg.get('type') == 'extension':
        tv_name = (msg.get('name') or 'TV ?').strip()
        tv_id   = tv_name  # stable key = display name

        # Register (or replace) this TV
        if tv_id not in ext_clients:
            ext_clients[tv_id] = {'ws': ws, 'name': tv_name, 'state': {}}
        else:
            ext_clients[tv_id]['ws']   = ws
            ext_clients[tv_id]['name'] = tv_name

        print(f'[+] Extension connectée: {tv_name}')
        await ws.send_str(json.dumps({
            'type': 'ack', 'ip': local_ip, 'http_port': PORT, 'tv_id': tv_id
        }))

        # Notify watching mobiles that the ext is now online
        await notify_watching(tv_id, json.dumps({'type': 'ext_status', 'connected': True}))
        await broadcast_tv_list()

        try:
            async for msg_data in ws:
                if msg_data.type == WSMsgType.TEXT:
                    d = json.loads(msg_data.data)
                    if d.get('type') == 'state':
                        ext_clients[tv_id]['state'] = d
                        await notify_watching(tv_id, msg_data.data)
                    # pong silently ignored
        except Exception:
            pass
        finally:
            # Mark disconnected but keep entry so mobile can see "offline" status
            if ext_clients.get(tv_id, {}).get('ws') is ws:
                ext_clients[tv_id]['ws'] = None
            print(f'[-] Extension déconnectée: {tv_name}')
            await notify_watching(tv_id, json.dumps({'type': 'ext_status', 'connected': False}))
            await broadcast_tv_list()

    # ── Mobile client ──────────────────────────────────────────────────────────
    elif msg.get('type') == 'mobile':
        mob_clients.add(ws)
        mob_tv_sel[id(ws)] = None
        print(f'[+] Mobile connecté ({len(mob_clients)} actif(s))')
        await ws.send_str(json.dumps({'type': 'auth_ok'}))
        await ws.send_str(json.dumps({'type': 'tv_list', 'tvs': tv_snapshot()}))

        try:
            async for msg_data in ws:
                if msg_data.type != WSMsgType.TEXT:
                    continue
                d = json.loads(msg_data.data)

                if d.get('type') == 'pong':
                    continue

                if d.get('type') == 'select_tv':
                    tv_id = d.get('id', '')
                    mob_tv_sel[id(ws)] = tv_id
                    info = ext_clients.get(tv_id, {})
                    ext_ws = info.get('ws')
                    connected = ext_ws is not None and not ext_ws.closed
                    await ws.send_str(json.dumps({'type': 'ext_status', 'connected': connected}))
                    state = info.get('state', {})
                    if state:
                        await ws.send_str(json.dumps({**state, 'type': 'state'}))

                elif d.get('type') == 'deselect_tv':
                    mob_tv_sel[id(ws)] = None
                    await ws.send_str(json.dumps({'type': 'deselected'}))
                    await ws.send_str(json.dumps({'type': 'tv_list', 'tvs': tv_snapshot()}))

                elif d.get('type') == 'command':
                    tv_id = mob_tv_sel.get(id(ws))
                    if tv_id:
                        info   = ext_clients.get(tv_id, {})
                        ext_ws = info.get('ws')
                        if ext_ws and not ext_ws.closed:
                            try:
                                await ext_ws.send_str(msg_data.data)
                            except Exception:
                                pass
                        else:
                            try:
                                await ws.send_str(json.dumps({'type': 'cmd_error', 'code': 'ext_offline'}))
                            except Exception:
                                pass
                    else:
                        try:
                            await ws.send_str(json.dumps({'type': 'cmd_error', 'code': 'no_tv_selected'}))
                        except Exception:
                            pass
        except Exception:
            pass
        finally:
            mob_clients.discard(ws)
            mob_tv_sel.pop(id(ws), None)
            print(f'[-] Mobile déconnecté ({len(mob_clients)} actif(s))')

    return ws

# ── Router ────────────────────────────────────────────────────────────────────

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

    # Ensure channels file exists
    if not CHANNELS_FILE.exists():
        save_channels([])

    print('╔══════════════════════════════════════════╗')
    print('║    wt-rotate Remote Control Server       ║')
    print('╠══════════════════════════════════════════╣')
    print(f'║  IP locale  : {local_ip:<27}║')
    print(f'║  URL mobile : {control_url:<27}║')
    print(f'║  QR code    : {"OK" if qr_cache else "manquant (pip install qrcode)":<27}║')
    print('╚══════════════════════════════════════════╝')
    print('\nEn attente de connexions…\n')

    app = web.Application()
    app.router.add_route('*', '/',         handle)
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
        input('Appuyez sur Entrée pour quitter…')
        raise SystemExit(1)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\nServeur arrêté.')
