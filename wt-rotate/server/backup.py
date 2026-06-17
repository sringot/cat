"""Sauvegarde de la playlist sur disque.

Le stockage de référence est chrome.storage.local côté extension : si le
profil Chrome saute (réinstallation, corruption…), la playlist est perdue.
Le serveur garde donc une copie de la dernière playlist non vide reçue,
restaurable depuis le téléphone (commande pl_restore).
"""
import json
import os
import time
from pathlib import Path

FILE = Path(__file__).parent.parent / 'playlist_backup.json'

# {'urls': [{'name','url','interval'}…], 'ts': epoch} — vide tant que rien reçu
data: dict = {'urls': [], 'ts': 0}


def load() -> None:
    global data
    try:
        raw = json.loads(FILE.read_text(encoding='utf-8'))
        if isinstance(raw.get('urls'), list):
            data = {'urls': raw['urls'], 'ts': raw.get('ts', 0)}
    except Exception:
        pass


def maybe_save(urls) -> bool:
    """Persiste la playlist si elle a changé. Retourne True si écrite.

    Une liste vide n'écrase JAMAIS une sauvegarde existante : une extension
    fraîchement réinstallée pousse un état vide, et c'est précisément le
    moment où la sauvegarde sert.
    """
    global data
    if not isinstance(urls, list):
        return False
    if not urls and data['urls']:
        return False
    if urls == data['urls']:
        return False
    data = {'urls': urls, 'ts': time.time()}
    # Écriture atomique : un .bat tué en plein write ne doit jamais laisser
    # un JSON tronqué (load() repartirait alors de zéro = playlist perdue).
    try:
        tmp = FILE.parent / (FILE.name + '.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        os.replace(tmp, FILE)
    except Exception:
        pass
    return True


def info_msg() -> dict:
    """Message backup_info pour les mobiles (affichage dans Réglages)."""
    return {'type': 'backup_info', 'count': len(data['urls']), 'ts': data['ts']}
