import asyncio
import ipaddress
import json
import logging
import time
from aiohttp import web, WSMsgType
from server import state, auth, sys_audio, backup, library

log = logging.getLogger('wt-rotate.ws')

# Adresses de bouclage : seule l'extension kiosque (même machine que le serveur)
# s'y connecte. Les téléphones arrivent eux par l'IP du LAN.
_LOOPBACK = {'127.0.0.1', '::1', 'localhost'}


def _is_local(request) -> bool:
    """True si la connexion vient de la machine locale (loopback)."""
    peer = (request.remote or '').strip()
    if peer in _LOOPBACK:
        return True
    try:
        return ipaddress.ip_address(peer).is_loopback
    except ValueError:
        return False


async def _reject(ws, reason: str) -> None:
    """Refuse une socket : prévient le client puis ferme proprement."""
    try:
        await ws.send_str(json.dumps({'type': 'auth_error', 'reason': reason}))
    except Exception:
        pass
    await ws.close()


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
        # L'extension kiosque tourne TOUJOURS sur la machine du serveur et s'y
        # connecte en ws://localhost (cf. manifest + bg/remote.js). On exige
        # une origine locale. ATTENTION : ça ne suffit PAS — une page web
        # ouverte dans le navigateur du kiosque se connecte aussi en loopback
        # (127.0.0.1). Sans le filtre d'origine ci-dessous, une page malveillante
        # affichée par la rotation pourrait s'annoncer comme « extension » avec
        # un token vide, récupérer le vrai token renvoyé dans l'ack (CSWSH) puis
        # piloter le kiosque. Le téléphone, lui, arrive par l'IP du LAN + token.
        if not _is_local(request):
            log.warning('Connexion extension refusée depuis %s (origine non locale)',
                        request.remote)
            await _reject(ws, 'local_only')
            return ws
        # Le navigateur fixe lui-même l'en-tête Origin ; une page web ne peut pas
        # la falsifier. Une vraie extension a une origine chrome-extension:// (ou
        # moz-extension://), ou aucune (clients locaux non-navigateurs). On refuse
        # donc toute origine web (http/https/ws…) → bloque le CSWSH depuis le
        # navigateur du kiosque sans casser l'amorçage de l'extension.
        origin = request.headers.get('Origin', '')
        if origin and not (origin.startswith('chrome-extension://') or
                           origin.startswith('moz-extension://')):
            log.warning('Connexion extension refusée (origine web « %s ») — CSWSH bloqué',
                        origin)
            await _reject(ws, 'bad_origin')
            return ws
        token = msg.get('token', '')
        if token and not auth.validate(token):
            await _reject(ws, 'invalid_token')
            return ws
        await _handle_extension(ws)
    elif msg.get('type') == 'mobile':
        if not auth.validate(msg.get('token', '')):
            await _reject(ws, 'invalid_token')
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
            log.warning('Conflit : plusieurs extensions kiosque connectées en même temps')
            await _broadcast_mobiles(json.dumps({'type': 'warn_dual_ext'}))
    log.info('Extension connectée')
    await ws.send_str(json.dumps({
        'type': 'ack', 'ip': state.local_ip, 'http_port': state.PORT,
        'control_url': f'http://{state.local_ip}:{state.PORT}/?token={auth.TOKEN}',
        'ext_token': auth.TOKEN
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
                    if backup.maybe_save(d.get('urls') or []):
                        await _broadcast_mobiles(json.dumps(backup.info_msg()))
                    await _broadcast_mobiles(msg_data.data)
                elif d.get('type') == 'screenshot':
                    # Mis en cache : un mobile qui arrive reçoit le dernier
                    # aperçu tout de suite au lieu d'attendre une capture
                    state.cached_shot = msg_data.data
                    state.cached_shot_ts = time.time()
                    await _broadcast_mobiles(msg_data.data)
                elif d.get('type') == 'cmd_ack':
                    await _broadcast_mobiles(msg_data.data)
                # pong responses silently ignored
    except Exception:
        pass
    finally:
        log.info('Extension déconnectée')
        if state.ext_ws is ws:
            # Only broadcast offline if no new extension took over during reconnect
            state.ext_ws = None
            await _broadcast_mobiles(json.dumps({'type': 'ext_status', 'connected': False}))
            try:
                from server import push as _push
                await _push.notify('Remote — Kiosque déconnecté',
                                   'Le PC kiosque s\'est déconnecté du serveur.')
            except ImportError:
                pass  # pywebpush non installé — notifications push désactivées
            except Exception:
                log.warning('Notification push de déconnexion échouée')


async def _handle_mobile(ws) -> None:
    state.mob_clients.add(ws)
    log.info('Mobile connecté (%d actif(s))', len(state.mob_clients))
    await ws.send_str(json.dumps({'type': 'auth_ok'}))
    ext_online = state.ext_ws is not None and not state.ext_ws.closed
    await ws.send_str(json.dumps({'type': 'ext_status', 'connected': ext_online}))
    if state.cached_state:
        await ws.send_str(json.dumps({**state.cached_state, 'type': 'state'}))
    await ws.send_str(json.dumps(backup.info_msg()))
    await ws.send_str(json.dumps(library.info_msg()))
    if state.cached_shot and time.time() - state.cached_shot_ts < 30:
        await ws.send_str(state.cached_shot)
    try:
        async for msg_data in ws:
            if msg_data.type == WSMsgType.TEXT:
                d = json.loads(msg_data.data)
                if d.get('type') == 'command':
                    payload = msg_data.data
                    # Bibliothèque de playlists — traitée côté serveur, pas forwardée
                    action = d.get('action', '')
                    if action == 'lib_save':
                        name = (d.get('name') or 'Playlist').strip()[:40] or 'Playlist'
                        urls = (state.cached_state or {}).get('urls') or []
                        if urls:
                            library.save_playlist(name, urls)
                            await _broadcast_mobiles(json.dumps(library.info_msg()))
                        continue
                    if action == 'lib_load':
                        pl = library.get_playlist(d.get('id') or '')
                        if pl and pl.get('urls'):
                            ext_cmd = json.dumps({'type': 'command', 'action': 'pl_restore', 'urls': pl['urls']})
                            if state.ext_ws and not state.ext_ws.closed:
                                try:
                                    await state.ext_ws.send_str(ext_cmd)
                                except Exception:
                                    pass
                            else:
                                try:
                                    await ws.send_str(json.dumps({'type': 'cmd_error', 'code': 'ext_offline'}))
                                except Exception:
                                    pass
                        continue
                    if action == 'lib_delete':
                        library.delete_playlist(d.get('id') or '')
                        await _broadcast_mobiles(json.dumps(library.info_msg()))
                        continue
                    # Captures : un frame vient d'être diffusé à TOUS les
                    # mobiles — inutile de redemander une capture identique
                    # quand plusieurs téléphones tournent en même temps.
                    # force=true (rafraîchissement manuel) court-circuite ce throttle.
                    if (d.get('action') == 'screenshot' and not d.get('force')
                            and time.time() - state.cached_shot_ts < 3):
                        continue
                    # Restauration : la playlist sauvegardée vit côté serveur,
                    # on l'injecte dans la commande avant de la forwarder.
                    if d.get('action') == 'pl_restore':
                        if not backup.data['urls']:
                            try:
                                await ws.send_str(json.dumps({
                                    'type': 'cmd_ack', 'action': 'pl_restore',
                                    'ok': False, 'reason': 'no_backup'}))
                            except Exception:
                                pass
                            continue
                        payload = json.dumps({**d, 'urls': backup.data['urls']})
                    # Volume : pycaw règle le volume système Windows quand il
                    # est dispo ; la vidéo est alors laissée à 100 % pour ne
                    # pas appliquer l'atténuation deux fois (50 % × 50 % = 25 %).
                    # Sans pycaw, le niveau est forwardé tel quel et c'est le
                    # <video> qui sert de bouton de volume.
                    if d.get('action') == 'volume':
                        try:
                            if sys_audio.set_volume(int(float(d.get('level', 100)))):
                                payload = json.dumps({**d, 'level': 100})
                        except (TypeError, ValueError):
                            pass  # level absent/malformé : on n'éjecte pas le mobile
                    if state.ext_ws and not state.ext_ws.closed:
                        try:
                            await state.ext_ws.send_str(payload)
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
        log.info('Mobile déconnecté (%d actif(s))', len(state.mob_clients))


async def keepalive_loop() -> None:
    """Pings applicatifs toutes les 20 s : maintiennent vivants le service
    worker de l'extension et les connexions mobiles. Chaque itération est
    isolée — une erreur transitoire ne doit jamais tuer la boucle, sinon les
    pings s'arrêtent en silence et les sockets finissent par tomber."""
    ping = json.dumps({'type': 'ping'})
    while True:
        try:
            await asyncio.sleep(20)
            if state.ext_ws and not state.ext_ws.closed:
                try:
                    await state.ext_ws.send_str(ping)
                except Exception:
                    pass
            await _broadcast_mobiles(ping)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('keepalive : itération en échec, on continue')
