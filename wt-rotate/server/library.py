import json
import os
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

FILE = Path(__file__).parent.parent / 'library.json'
data: dict = {'playlists': []}


def _host(url: str) -> str:
    """Hôte normalisé (sans www) d'une URL, tolérant aux URLs sans schéma."""
    s = (url or '').strip()
    if not s:
        return ''
    if '://' not in s:
        s = 'http://' + s
    try:
        h = (urlparse(s).hostname or '').lower()
    except Exception:
        return ''
    return h[4:] if h.startswith('www.') else h


def _hosts(urls: list, limit: int = 4) -> list:
    """Jusqu'à `limit` hôtes distincts, pour la mosaïque de favicons."""
    out: list = []
    for u in urls:
        h = _host(u.get('url'))
        if h and h not in out:
            out.append(h)
            if len(out) >= limit:
                break
    return out


def load() -> None:
    global data
    try:
        d = json.loads(FILE.read_text(encoding='utf-8'))
        data = {'playlists': d.get('playlists', [])}
    except Exception:
        data = {'playlists': []}


def save_playlist(name: str, urls: list) -> None:
    entry = {
        'id': uuid.uuid4().hex[:8],
        'name': (name[:40].strip()) or 'Playlist',
        'urls': [u for u in urls if u.get('url')],
        'ts': time.time(),
    }
    data['playlists'].append(entry)
    _persist()


def delete_playlist(pid: str) -> bool:
    before = len(data['playlists'])
    data['playlists'] = [p for p in data['playlists'] if p['id'] != pid]
    changed = len(data['playlists']) < before
    if changed:
        _persist()
    return changed


def get_playlist(pid: str):
    return next((p for p in data['playlists'] if p['id'] == pid), None)


def info_msg() -> dict:
    return {
        'type': 'library_update',
        'playlists': [
            {
                'id': p['id'],
                'name': p['name'],
                'count': len(p.get('urls', [])),
                'hosts': _hosts(p.get('urls', [])),
                'ts': p['ts'],
            }
            for p in data['playlists']
        ],
    }


def _persist() -> None:
    # Écriture atomique (cf. backup.py) : pas de bibliothèque corrompue si le
    # serveur est tué pendant la sauvegarde.
    try:
        tmp = FILE.parent / (FILE.name + '.tmp')
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8'
        )
        os.replace(tmp, FILE)
    except Exception:
        pass
