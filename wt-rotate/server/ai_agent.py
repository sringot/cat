"""
Assistant vocal IA — pilote le kiosque en langage naturel.
Requiert : pip install anthropic
Variable d'environnement : ANTHROPIC_API_KEY
"""
import asyncio
import json
import os
import re
import urllib.parse

_client = None
_MODEL  = 'claude-haiku-4-5-20251001'

TOOLS = [
    {
        "name": "search_youtube",
        "description": (
            "Recherche une vidéo YouTube et retourne l'URL de la première correspondance. "
            "Utilise recent=true pour trouver la vidéo la plus récente d'une chaîne."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Requête de recherche (ex: 'Squeezie vlog', 'tutoriel Python débutant')"
                },
                "recent": {
                    "type": "boolean",
                    "description": "true pour trier par date de mise en ligne (dernière vidéo d'une chaîne)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "kiosk_command",
        "description": "Envoie une commande au kiosque d'affichage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["open_url", "pause", "resume", "next", "prev", "release", "announce"],
                    "description": "Commande à exécuter"
                },
                "url":      {"type": "string",  "description": "URL à afficher (pour open_url)"},
                "duration": {"type": "integer", "description": "Durée d'affichage en secondes (open_url: 0=permanent; announce: durée du bandeau)"},
                "text":     {"type": "string",  "description": "Texte du bandeau (pour announce)"}
            },
            "required": ["action"]
        }
    }
]

_SYSTEM = """\
Tu es l'assistant vocal du kiosque d'affichage "wee rotate".
Tu pilotes un écran TV/kiosque dans un bureau ou espace professionnel.
Utilise toujours les outils AVANT de répondre. Sois ultra-concis (une phrase max). Parle en français.

État actuel du kiosque :
{state}\
"""


def init() -> None:
    global _client
    key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if not key:
        return
    try:
        from anthropic import AsyncAnthropic
        _client = AsyncAnthropic(api_key=key)
        print(f'[IA] Assistant vocal actif (modèle : {_MODEL})')
    except ImportError:
        print('[IA] anthropic non installé — pip install anthropic')


def is_available() -> bool:
    return _client is not None


async def search_youtube(query: str, recent: bool = False) -> dict:
    """YouTube search via page scraping (pas d'API key requise). Fallback sur yt-dlp."""
    from aiohttp import ClientSession, ClientTimeout

    sort_param = '&sp=CAI%3D' if recent else ''
    encoded = urllib.parse.quote_plus(query)
    url = f'https://www.youtube.com/results?search_query={encoded}{sort_param}'
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
    }
    try:
        async with ClientSession(timeout=ClientTimeout(total=12)) as sess:
            async with sess.get(url, headers=headers) as resp:
                html = await resp.text(errors='replace')
        # Les IDs vidéo sont de la forme "videoId":"XXXXXXXXXXX" (exactement 11 chars)
        ids = re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', html)
        seen: set = set()
        unique = [v for v in ids if not (v in seen or seen.add(v))]  # type: ignore[func-returns-value]
        if unique:
            return {'ok': True, 'url': f'https://www.youtube.com/watch?v={unique[0]}'}
    except Exception:
        pass

    # Fallback : yt-dlp (si installé)
    try:
        proc = await asyncio.create_subprocess_exec(
            'yt-dlp', '--no-playlist', '--dump-single-json', '--playlist-items', '1',
            f'ytsearch1:{query}',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
        if proc.returncode == 0 and stdout:
            data = json.loads(stdout.decode())
            vid_id = data.get('id', '')
            if vid_id:
                return {'ok': True, 'url': f'https://www.youtube.com/watch?v={vid_id}'}
    except Exception:
        pass

    return {'ok': False, 'error': 'Recherche YouTube indisponible'}


async def run(text: str, kiosk_state: dict) -> dict:
    """Exécute l'agent IA. Retourne {'reply': str, 'commands': list[dict]}."""
    if not _client:
        return {
            'reply': "Assistant IA non configuré — définissez ANTHROPIC_API_KEY.",
            'commands': [],
        }

    state_desc = _describe_state(kiosk_state)
    messages: list = [{'role': 'user', 'content': text}]
    commands: list = []

    for _ in range(5):  # max 5 rounds d'outils
        resp = await _client.messages.create(
            model=_MODEL,
            max_tokens=512,
            system=_SYSTEM.format(state=state_desc),
            tools=TOOLS,
            messages=messages,
        )
        tool_uses  = [b for b in resp.content if b.type == 'tool_use']
        text_parts = [b.text for b in resp.content if b.type == 'text']

        if not tool_uses:
            reply = text_parts[0].strip() if text_parts else 'Fait !'
            return {'reply': reply, 'commands': commands}

        tool_results = []
        for tu in tool_uses:
            if tu.name == 'search_youtube':
                result = await search_youtube(
                    tu.input.get('query', ''),
                    recent=bool(tu.input.get('recent', False)),
                )
                tool_results.append({
                    'type': 'tool_result',
                    'tool_use_id': tu.id,
                    'content': json.dumps(result),
                })
            elif tu.name == 'kiosk_command':
                commands.append(dict(tu.input))
                tool_results.append({
                    'type': 'tool_result',
                    'tool_use_id': tu.id,
                    'content': '{"ok": true}',
                })

        messages.append({'role': 'assistant', 'content': resp.content})
        messages.append({'role': 'user', 'content': tool_results})

    return {'reply': 'Fait !', 'commands': commands}


def _describe_state(s: dict) -> str:
    if not s:
        return 'Kiosque non connecté'
    parts = []
    if s.get('active'):
        parts.append('Rotation active')
    elif s.get('remotePaused') and s.get('remoteUrl'):
        parts.append(f"URL externe affichée : {s.get('remoteUrl')}")
    elif s.get('remotePaused'):
        parts.append('Rotation en pause')
    else:
        parts.append('Rotation arrêtée')
    urls = s.get('urls', [])
    if urls:
        ci = s.get('currentIndex', 0)
        names = [u.get('name') or u.get('url', '') for u in urls]
        parts.append(f"{len(urls)} page(s) dans la playlist : " + ', '.join(names[:6]))
        if 0 <= ci < len(names):
            parts.append(f"Page actuelle : {names[ci]}")
    return '\n'.join(parts)
