"""Tests de la sauvegarde de playlist (server/backup.py).

Invariant critique : une liste vide ne doit JAMAIS écraser une sauvegarde
existante (une extension fraîchement réinstallée pousse un état vide, et c'est
précisément le moment où la sauvegarde sert)."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from server import backup


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        backup.FILE = self.tmp / 'playlist_backup.json'
        backup.data = {'urls': [], 'ts': 0}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_on_empty_noop(self):
        self.assertFalse(backup.maybe_save([]))
        self.assertFalse(backup.FILE.exists())

    def test_save_writes_valid_json(self):
        urls = [{'name': 'A', 'url': 'https://a.test', 'interval': None}]
        self.assertTrue(backup.maybe_save(urls))
        self.assertTrue(backup.FILE.exists())
        on_disk = json.loads(backup.FILE.read_text(encoding='utf-8'))
        self.assertEqual(on_disk['urls'], urls)
        self.assertIn('ts', on_disk)

    def test_unchanged_not_rewritten(self):
        urls = [{'name': 'A', 'url': 'https://a.test', 'interval': None}]
        self.assertTrue(backup.maybe_save(urls))
        # Même contenu → pas de réécriture
        self.assertFalse(backup.maybe_save(list(urls)))

    def test_empty_does_not_clobber(self):
        urls = [{'name': 'A', 'url': 'https://a.test', 'interval': None}]
        self.assertTrue(backup.maybe_save(urls))
        # La liste vide doit être refusée et la sauvegarde rester intacte
        self.assertFalse(backup.maybe_save([]))
        self.assertEqual(backup.data['urls'], urls)
        on_disk = json.loads(backup.FILE.read_text(encoding='utf-8'))
        self.assertEqual(on_disk['urls'], urls)

    def test_non_list_rejected(self):
        self.assertFalse(backup.maybe_save('not-a-list'))
        self.assertFalse(backup.maybe_save(None))

    def test_atomic_write_leaves_no_tmp(self):
        backup.maybe_save([{'url': 'https://a.test'}])
        leftovers = list(self.tmp.glob('*.tmp'))
        self.assertEqual(leftovers, [])

    def test_load_tolerates_corruption(self):
        backup.FILE.write_text('{ this is not json', encoding='utf-8')
        backup.data = {'urls': [{'url': 'x'}], 'ts': 1}
        backup.load()  # ne doit pas lever
        self.assertIn('urls', backup.data)

    def test_load_reads_back(self):
        payload = {'urls': [{'name': 'B', 'url': 'https://b.test', 'interval': 30}], 'ts': 123}
        backup.FILE.write_text(json.dumps(payload), encoding='utf-8')
        backup.data = {'urls': [], 'ts': 0}
        backup.load()
        self.assertEqual(backup.data['urls'], payload['urls'])

    def test_info_msg_shape(self):
        backup.maybe_save([{'url': 'https://a.test'}])
        msg = backup.info_msg()
        self.assertEqual(msg['type'], 'backup_info')
        self.assertEqual(msg['count'], 1)
        self.assertIn('ts', msg)


if __name__ == '__main__':
    unittest.main()
