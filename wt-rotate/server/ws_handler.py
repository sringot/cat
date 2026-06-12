import asyncio
import json
import time
from aiohttp import web, WSMsgType
from server import state, auth, sys_audio


async def _broadcast_mobiles(msg: str) -> None:
    """Send a message to all connected mobiles, pruning dead connections."""
    dead = set()
    for m in list(state.mob_clients):
        if m.closed:
            dead.add(m)
            continue
        try:
            await m.send_str(msg)
        except Exception:
            dead.add(m)
    state.mob_clients -= dead


async def handle_ws(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    try:
        first = await asyncio.wait_for(ws.receive(), timeout=10)
        if first.type != WSMsgType.TEXT:
            return ws
        msg = json.loads(first.data)
    except Exception:
        return ws

    if msg.get('type') == 'extension':
        await _handle_extension(ws)
    elif msg.get('type') == 'mobile':
        if not auth.validate(msg.get('token', '')):
            try:
                await ws.send_str(json.dumps({'type': 'auth_error', 'reason': 'invalid_token'}))
            except Exception:
                pass
            await ws.close()
            return ws
        await _handle_mobile(ws)

    return ws


async def _handle_extension(ws) -> None:
    # Un seul kiosque à la fois : la nouvelle connexion évince l'ancienne,
    # sinon les deux diffusent leurs états et le téléphone voit la config
    # de l'une puis de l'autre (doublon d'extension, Chrome + Edge…).
    prev = state.ext_ws
    state.ext_ws = ws
    if prev is not None and not prev.closed:
        # Éviction d'une connexion encore vivante : si ça se répète, c'est
        # que DEUX extensions se battent — on prévient les téléphones.
        now = time.time()
        state.ext_takeovers = [t for t in state.ext_takeovers if now - t < 30]
        state.ext_takeovers.append(now)
        try:
            await prev.close()
        except Exception:
            pass
        if len(state.ext_takeovers) >= 3:
            print('[!] CONFLIT : plusieurs extensions kiosque connectées en même temps')
            await _broadcast_mobiles(json.dumps({'type': 'warn_dual_ext'}))
    print('[+] Extension connectée')
    await ws.send_str(json.dumps({
        'type': 'ack', 'ip': state.local_ip, 'http_port': state.PORT,
        'control_url': f'http://{state.local_ip}:{state.PORT}/?token={auth.TOKEN}'
    }))
    await _broadcast_mobiles(json.dumps({'type': 'ext_status', 'connected': True}))
    try:
        async for msg_data in ws:
            if state.ext_ws is not ws:
                break  # connexion évincée : elle ne diffuse plus rien
            if msg_data.type == WSMsgType.TEXT:
                d = json.loads(msg_data.data)
                if d.get('type') == 'state':
                    state.cached_state = d
                    await _broadcast_mobiles(msg_data.data)
                elif d.get('type') in ('cmd_ack', 'screenshot'):
                    await _broadcast_mobiles(msg_data.data)
                # pong responses silently ignored
    except Exception:
        pass
    finally:
        print('[-] Extension déconnectée')
        if state.ext_ws is ws:
            # Only broadcast offline if no new extension took over during reconnect
            state.ext_ws = None
            await _broadcast_mobiles(json.dumps({'type': 'ext_status', 'connected': False}))


async def _handle_mobile(ws) -> None:
    state.mob_clients.add(ws)
    print(f'[+] Mobile connecté ({len(state.mob_clients)} actif(s))')
    await ws.send_str(json.dumps({'type': 'auth_ok'}))
    ext_online = state.ext_ws is not None and not state.ext_ws.closed
    await ws.send_str(json.dumps({'type': 'ext_status', 'connected': ext_online}))
    if state.cached_state:
        await ws.send_str(json.dumps({**state.cached_state, 'type': 'state'}))
    try:
        async for msg_data in ws:
            if msg_data.type == WSMsgType.TEXT:
                d = json.loads(msg_data.data)
                if d.get('type') == 'command':
                    # Volume système : on règle pycaw côté serveur, puis on
                    # forwarde aussi à l'extension pour le <video> HTML5
                    if d.get('action') == 'volume':
                        sys_audio.set_volume(int(d.get('level', 100)))
                    if state.ext_ws and not state.ext_ws.closed:
                        try:
                            await state.ext_ws.send_str(msg_data.data)
                        except Exception:
                            pass
                    else:
                        try:
                            await ws.send_str(json.dumps({'type': 'cmd_error', 'code': 'ext_offline'}))
                        except Exception:
                            pass
                # pong responses silently ignored
    except Exception:
        pass
    finally:
        state.mob_clients.discard(ws)
        print(f'[-] Mobile déconnecté ({len(state.mob_clients)} actif(s))')


async def keepalive_loop() -> None:
    """Application-level pings every 20s keep extension SW and mobile connections alive."""
    ping = json.dumps({'type': 'ping'})
    while True:
        await asyncio.sleep(20)
        if state.ext_ws and not state.ext_ws.closed:
            try:
                await state.ext_ws.send_str(ping)
            except Exception:
                pass
        await _broadcast_mobiles(ping)
