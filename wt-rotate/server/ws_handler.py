import asyncio
import json
from aiohttp import web, WSMsgType
from server import state, auth


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
    state.ext_ws = ws
    print('[+] Extension connectée')
    await ws.send_str(json.dumps({'type': 'ack', 'ip': state.local_ip, 'http_port': state.PORT}))
    await _broadcast_mobiles(json.dumps({'type': 'ext_status', 'connected': True}))
    try:
        async for msg_data in ws:
            if msg_data.type == WSMsgType.TEXT:
                d = json.loads(msg_data.data)
                if d.get('type') == 'state':
                    state.cached_state = d
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
