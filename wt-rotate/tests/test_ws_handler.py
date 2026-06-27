"""Tests du handler WebSocket (server/ws_handler.py).

Le cœur sécurité : une page web ouverte dans le navigateur du kiosque se
connecte aussi en loopback — seul le filtre d'origine empêche un CSWSH
(une page malveillante s'annonçant « extension » pour voler le token)."""
import asyncio
import types
import unittest

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from server import state, auth, ws_handler, library
from server.ws_handler import handle_ws, _is_local
from server.http_handler import handle_http


async def _dispatch(request):
    if request.headers.get('Upgrade', '').lower() == 'websocket':
        return await handle_ws(request)
    return await handle_http(request)


class IsLocalTests(unittest.TestCase):
    def _req(self, remote):
        return types.SimpleNamespace(remote=remote)

    def test_loopback_names(self):
        for r in ('127.0.0.1', '::1', 'localhost'):
            self.assertTrue(_is_local(self._req(r)))

    def test_loopback_range(self):
        self.assertTrue(_is_local(self._req('127.0.0.5')))

    def test_lan_ip_rejected(self):
        self.assertFalse(_is_local(self._req('192.168.1.20')))

    def test_empty_rejected(self):
        self.assertFalse(_is_local(self._req('')))
        self.assertFalse(_is_local(self._req(None)))


class WSHandshakeTests(AioHTTPTestCase):
    async def get_application(self):
        app = web.Application()
        app.router.add_get('/', _dispatch)
        app.router.add_get('/{path:.+}', _dispatch)
        return app

    async def asyncSetUp(self):
        await super().asyncSetUp()
        state.ext_ws = None
        state.mob_clients = set()
        state.ext_takeovers = []

    async def test_extension_web_origin_rejected(self):
        ws = await self.client.ws_connect('/', headers={'Origin': 'https://evil.example'})
        await ws.send_json({'type': 'extension', 'token': ''})
        msg = await ws.receive_json()
        self.assertEqual(msg['type'], 'auth_error')
        self.assertEqual(msg['reason'], 'bad_origin')
        await ws.close()

    async def test_extension_chrome_origin_accepted(self):
        ws = await self.client.ws_connect('/', headers={'Origin': 'chrome-extension://abcdef'})
        await ws.send_json({'type': 'extension', 'token': ''})
        msg = await ws.receive_json()
        self.assertEqual(msg['type'], 'ack')
        self.assertEqual(msg['ext_token'], auth.TOKEN)
        await ws.close()

    async def test_extension_null_origin_accepted(self):
        ws = await self.client.ws_connect('/', headers={'Origin': 'null'})
        await ws.send_json({'type': 'extension', 'token': ''})
        msg = await ws.receive_json()
        self.assertEqual(msg['type'], 'ack')
        await ws.close()

    async def test_extension_bad_token_rejected(self):
        ws = await self.client.ws_connect('/', headers={'Origin': 'chrome-extension://abcdef'})
        await ws.send_json({'type': 'extension', 'token': 'wrong-token-value'})
        msg = await ws.receive_json()
        self.assertEqual(msg['type'], 'auth_error')
        self.assertEqual(msg['reason'], 'invalid_token')
        await ws.close()

    async def test_mobile_bad_token_rejected(self):
        ws = await self.client.ws_connect('/')
        await ws.send_json({'type': 'mobile', 'token': 'nope'})
        msg = await ws.receive_json()
        self.assertEqual(msg['type'], 'auth_error')
        self.assertEqual(msg['reason'], 'invalid_token')
        await ws.close()

    async def test_mobile_valid_token_accepted(self):
        ws = await self.client.ws_connect('/')
        await ws.send_json({'type': 'mobile', 'token': auth.TOKEN})
        msg = await ws.receive_json()
        self.assertEqual(msg['type'], 'auth_ok')
        await ws.close()


class LibCreateTests(AioHTTPTestCase):
    """Commande lib_create : une playlist bâtie sur le téléphone (brouillon
    hors-ligne) est enregistrée côté serveur à partir des URLs reçues."""

    async def get_application(self):
        app = web.Application()
        app.router.add_get('/', _dispatch)
        app.router.add_get('/{path:.+}', _dispatch)
        return app

    async def asyncSetUp(self):
        await super().asyncSetUp()
        state.ext_ws = None
        state.mob_clients = set()
        state.cached_state = None
        state.cached_shot = None
        library.data = {'playlists': []}

    async def _await_library_update(self, ws, name):
        """Boucle de réception jusqu'au library_update contenant `name`."""
        for _ in range(8):
            msg = await asyncio.wait_for(ws.receive_json(), timeout=2)
            if msg.get('type') == 'library_update' and \
                    any(p['name'] == name for p in msg.get('playlists', [])):
                return msg
        return None

    async def test_lib_create_saves_phone_built_playlist(self):
        ws = await self.client.ws_connect('/')
        await ws.send_json({'type': 'mobile', 'token': auth.TOKEN})
        await ws.send_json({'type': 'command', 'action': 'lib_create',
                            'name': 'Hors-ligne',
                            'urls': [{'url': 'https://a.test', 'name': 'A', 'interval': None},
                                     {'url': 'https://b.test', 'name': '', 'interval': 60}]})
        msg = await self._await_library_update(ws, 'Hors-ligne')
        await ws.close()
        self.assertIsNotNone(msg, 'la playlist créée doit être diffusée aux mobiles')
        pl = next(p for p in msg['playlists'] if p['name'] == 'Hors-ligne')
        self.assertEqual(pl['count'], 2)
        # Et elle est bien stockée côté serveur, avec ses URLs.
        self.assertEqual(len(library.data['playlists']), 1)
        self.assertEqual(library.data['playlists'][0]['urls'][0]['url'], 'https://a.test')

    async def test_lib_create_ignores_empty_and_malformed_urls(self):
        ws = await self.client.ws_connect('/')
        await ws.send_json({'type': 'mobile', 'token': auth.TOKEN})
        # Aucune URL exploitable → rien créé.
        await ws.send_json({'type': 'command', 'action': 'lib_create', 'name': 'Vide',
                            'urls': [{'name': 'pas d_url'}, 'chaine', None]})
        # 2e commande valide en sentinelle : sa diffusion prouve que la 1re est
        # déjà traitée (FIFO) — sans avoir rien créé.
        await ws.send_json({'type': 'command', 'action': 'lib_create', 'name': 'Sentinelle',
                            'urls': [{'url': 'https://s.test'}]})
        msg = await self._await_library_update(ws, 'Sentinelle')
        await ws.close()
        self.assertIsNotNone(msg)
        self.assertEqual([p['name'] for p in library.data['playlists']], ['Sentinelle'])


if __name__ == '__main__':
    unittest.main()
