import json
import time
import uuid
from pathlib import Path

FILE = Path(__file__).parent.parent / 'library.json'
data: dict = {'playlists': []}


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
                'ts': p['ts'],
            }
            for p in data['playlists']
        ],
    }


def _persist() -> None:
    try:
        FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8'
        )
    except Exception:
        pass
