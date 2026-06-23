"""Tests de la bibliothèque de playlists (server/library.py)."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from server import library


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        library.FILE = self.tmp / 'library.json'
        library.data = {'playlists': []}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_and_get_roundtrip(self):
        library.save_playlist('Accueil', [{'url': 'https://a.test', 'name': 'A'}])
        self.assertEqual(len(library.data['playlists']), 1)
        pid = library.data['playlists'][0]['id']
        entry = library.get_playlist(pid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry['name'], 'Accueil')

    def test_urls_without_url_are_dropped(self):
        library.save_playlist('Mix', [{'url': 'https://a.test'}, {'name': 'no url'}])
        self.assertEqual(len(library.data['playlists'][0]['urls']), 1)

    def test_empty_name_defaults(self):
        library.save_playlist('   ', [{'url': 'https://a.test'}])
        self.assertEqual(library.data['playlists'][0]['name'], 'Playlist')

    def test_name_truncated_to_40(self):
        library.save_playlist('x' * 100, [{'url': 'https://a.test'}])
        self.assertLessEqual(len(library.data['playlists'][0]['name']), 40)

    def test_cap_enforced(self):
        for i in range(library.MAX_PLAYLISTS):
            library.save_playlist(f'P{i}', [{'url': f'https://{i}.test'}])
        self.assertEqual(len(library.data['playlists']), library.MAX_PLAYLISTS)
        # Le suivant est ignoré silencieusement
        library.save_playlist('overflow', [{'url': 'https://x.test'}])
        self.assertEqual(len(library.data['playlists']), library.MAX_PLAYLISTS)
        self.assertNotIn('overflow', [p['name'] for p in library.data['playlists']])

    def test_delete_existing_and_missing(self):
        library.save_playlist('A', [{'url': 'https://a.test'}])
        pid = library.data['playlists'][0]['id']
        self.assertTrue(library.delete_playlist(pid))
        self.assertEqual(len(library.data['playlists']), 0)
        self.assertFalse(library.delete_playlist('does-not-exist'))

    def test_get_missing_returns_none(self):
        self.assertIsNone(library.get_playlist('nope'))

    def test_persist_atomic_no_tmp(self):
        library.save_playlist('A', [{'url': 'https://a.test'}])
        self.assertTrue(library.FILE.exists())
        json.loads(library.FILE.read_text(encoding='utf-8'))  # JSON valide
        self.assertEqual(list(self.tmp.glob('*.tmp')), [])

    def test_host_normalization(self):
        self.assertEqual(library._host('https://www.example.com/p'), 'example.com')
        self.assertEqual(library._host('http://Example.COM'), 'example.com')
        self.assertEqual(library._host('example.com/x'), 'example.com')
        self.assertEqual(library._host(''), '')

    def test_hosts_dedup_and_limit(self):
        urls = [{'url': 'https://a.com'}, {'url': 'https://a.com'}, {'url': 'https://b.com'}]
        self.assertEqual(library._hosts(urls), ['a.com', 'b.com'])
        many = [{'url': f'https://h{i}.com'} for i in range(10)]
        self.assertEqual(len(library._hosts(many, limit=4)), 4)

    def test_info_msg_shape(self):
        library.save_playlist('A', [{'url': 'https://a.test'}])
        msg = library.info_msg()
        self.assertEqual(msg['type'], 'library_update')
        self.assertEqual(len(msg['playlists']), 1)
        self.assertEqual(msg['playlists'][0]['count'], 1)


if __name__ == '__main__':
    unittest.main()
