"""Tests du handler HTTP (server/http_handler.py).

Point sécurité majeur : /qr.svg encode l'URL + le token et ne doit donc PAS
porter d'en-tête CORS « * » (sinon une page web tierce pourrait fetch le SVG
et en extraire le token)."""
import unittest

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from server import state
from server.http_handler import handle_http


class HTTPTests(AioHTTPTestCase):
    async def get_application(self):
        app = web.Application()
        app.router.add_route('*', '/{path:.*}', handle_http)
        return app

    async def asyncSetUp(self):
        await super().asyncSetUp()
        state.qr_cache = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'
        state.guide_cache = b'<html>guide</html>'
        state.html_cache = b'<html>app</html>'

    async def test_qr_has_no_cors(self):
        resp = await self.client.get('/qr.svg')
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.headers['Content-Type'], 'image/svg+xml')
        # L'absence de CORS est l'invariant sécurité
        self.assertNotIn('Access-Control-Allow-Origin', resp.headers)

    async def test_qr_missing_returns_503(self):
        state.qr_cache = None
        resp = await self.client.get('/qr.svg')
        self.assertEqual(resp.status, 503)

    async def test_info_has_cors(self):
        resp = await self.client.get('/info')
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.headers.get('Access-Control-Allow-Origin'), '*')
        body = await resp.json()
        self.assertIn('ip', body)
        self.assertIn('http_port', body)

    async def test_sw_js_served(self):
        resp = await self.client.get('/sw.js')
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.headers['Content-Type'], 'application/javascript')
        self.assertEqual(resp.headers.get('Service-Worker-Allowed'), '/')

    async def test_root_serves_guide(self):
        resp = await self.client.get('/')
        self.assertEqual(resp.status, 200)
        self.assertIn('text/html', resp.headers['Content-Type'])
        self.assertIn('guide', await resp.text())

    async def test_app_serves_control(self):
        resp = await self.client.get('/app')
        self.assertEqual(resp.status, 200)
        self.assertIn('text/html', resp.headers['Content-Type'])

    async def test_support_served(self):
        # Centre d'aide autonome — sert le fichier support.html du dépôt.
        resp = await self.client.get('/support')
        self.assertEqual(resp.status, 200)
        self.assertIn('text/html', resp.headers['Content-Type'])
        self.assertIn("Centre d'aide", await resp.text())

    async def test_aide_is_support_alias(self):
        resp = await self.client.get('/aide')
        self.assertEqual(resp.status, 200)
        self.assertIn('text/html', resp.headers['Content-Type'])


if __name__ == '__main__':
    unittest.main()
