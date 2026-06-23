"""Tests du handler WebSocket (server/ws_handler.py).

Le cœur sécurité : une page web ouverte dans le navigateur du kiosque se
connecte aussi en loopback — seul le filtre d'origine empêche un CSWSH
(une page malveillante s'annonçant « extension » pour voler le token)."""
import types
import unittest

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from server import state, auth, ws_handler
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
        # Neutralise la notif push de déconnexion (réseau + génération de clés)
        import server.push as push_mod
        self._orig_notify = push_mod.notify

        async def _noop(*a, **k):
            return None

        push_mod.notify = _noop

    async def asyncTearDown(self):
        import server.push as push_mod
        push_mod.notify = self._orig_notify
        await super().asyncTearDown()

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


if __name__ == '__main__':
    unittest.main()
