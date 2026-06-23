"""Tests des abonnements push (server/push.py).

Couvre les garde-fous anti-DoS (cap 100, taille max), l'écriture atomique,
la déduplication par endpoint et le pruning parallèle des abonnés expirés."""
import asyncio
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from server import push


class PushTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        push._SUBS_FILE = self.tmp / 'subs.json'

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    async def test_save_and_load(self):
        await push.save_subscription({'endpoint': 'https://e/1', 'keys': {}})
        self.assertEqual(len(push._load_subs()), 1)

    async def test_dedup_by_endpoint(self):
        await push.save_subscription({'endpoint': 'https://e/1', 'keys': {'a': 1}})
        await push.save_subscription({'endpoint': 'https://e/1', 'keys': {'a': 2}})
        subs = push._load_subs()
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0]['keys'], {'a': 2})

    async def test_missing_endpoint_ignored(self):
        await push.save_subscription({})
        await push.save_subscription({'keys': {}})
        self.assertEqual(len(push._load_subs()), 0)

    async def test_non_string_endpoint_ignored(self):
        await push.save_subscription({'endpoint': 123})
        self.assertEqual(len(push._load_subs()), 0)

    async def test_oversized_rejected(self):
        await push.save_subscription({'endpoint': 'https://e', 'keys': {'p': 'A' * 5000}})
        self.assertEqual(len(push._load_subs()), 0)

    async def test_cap_100(self):
        push._save_subs([{'endpoint': f'https://e/{i}'} for i in range(100)])
        await push.save_subscription({'endpoint': 'https://e/new'})
        self.assertEqual(len(push._load_subs()), 100)
        self.assertNotIn('https://e/new', [s['endpoint'] for s in push._load_subs()])

    async def test_remove_subscription(self):
        push._save_subs([{'endpoint': 'https://e/1'}, {'endpoint': 'https://e/2'}])
        await push.remove_subscription('https://e/1')
        endpoints = [s['endpoint'] for s in push._load_subs()]
        self.assertEqual(endpoints, ['https://e/2'])

    def test_save_atomic_no_tmp(self):
        push._save_subs([{'endpoint': 'https://e/1'}])
        json.loads(push._SUBS_FILE.read_text())  # JSON valide
        self.assertEqual(list(self.tmp.glob('*.tmp')), [])

    async def test_notify_prunes_expired_in_parallel(self):
        # On force VAPID dispo et on remplace l'envoi réseau par un stub :
        # un endpoint « gone » renvoie 'expired' et doit être élagué, les
        # autres restent. On vérifie aussi que tous sont appelés (gather).
        push.VAPID_AVAILABLE = True
        push._save_subs([
            {'endpoint': 'https://e/1'},
            {'endpoint': 'https://e/gone'},
            {'endpoint': 'https://e/3'},
        ])
        calls = []
        orig = push._send_one

        def stub(sub, title, body):
            calls.append(sub['endpoint'])
            return 'expired' if 'gone' in sub['endpoint'] else True

        push._send_one = stub
        try:
            await push.notify('Titre', 'Corps')
        finally:
            push._send_one = orig

        self.assertEqual(len(calls), 3)
        remaining = [s['endpoint'] for s in push._load_subs()]
        self.assertIn('https://e/1', remaining)
        self.assertIn('https://e/3', remaining)
        self.assertNotIn('https://e/gone', remaining)

    async def test_notify_noop_without_subs(self):
        push.VAPID_AVAILABLE = True
        push._save_subs([])
        await push.notify('t', 'b')  # ne doit pas lever


if __name__ == '__main__':
    unittest.main()
