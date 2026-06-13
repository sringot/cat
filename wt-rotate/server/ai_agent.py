"""
Assistant vocal IA — agent de configuration du kiosque en langage naturel.
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

# Actions que l'IA a le droit d'envoyer au kiosque (whitelist ws_handler)
ALLOWED_ACTIONS = [
    'open_url', 'pause', 'resume', 'next', 'prev', 'release', 'announce',
    'goto', 'pl_add', 'pl_remove', 'pl_rename', 'pl_set_interval',
    'set_interval', 'set_schedule', 'reload_all',
]

TOOLS = [
    {
        "name": "search_web",
        "description": (
            "Recherche web (DuckDuckGo). Retourne les premières URLs avec leurs titres. "
            "À utiliser pour trouver l'URL d'un site (entreprise, service, outil) — "
            "ne devine JAMAIS une URL de mémoire."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Requête (ex: 'Wee Technology site officiel')"}
            },
            "required": ["query"]
        }
    },
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
        "description": "Envoie une commande au kiosque d'affichage (affichage, playlist, réglages).",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ALLOWED_ACTIONS,
                    "description": (
                        "open_url: afficher une URL temporairement (spotlight) · "
                        "pl_add: ajouter une page à la playlist (permanent) · "
                        "pl_remove/pl_rename/pl_set_interval: modifier une page (index requis) · "
                        "goto: afficher une page de la playlist (index requis) · "
                        "set_interval: intervalle global de rotation · "
                        "set_schedule: horaires d'affichage · "
                        "pause/resume/next/prev/release/reload_all/announce"
                    )
                },
                "url":      {"type": "string",  "description": "URL (open_url, pl_add)"},
                "duration": {"type": "integer", "description": "Durée en secondes (open_url: 0=permanent ; announce: durée du bandeau)"},
                "text":     {"type": "string",  "description": "Texte du bandeau (announce)"},
                "name":     {"type": "string",  "description": "Nom de la page (pl_add, pl_rename)"},
                "index":    {"type": "integer", "description": "Index de la page dans la playlist (goto, pl_remove, pl_rename, pl_set_interval) — voir l'état du kiosque"},
                "seconds":  {"type": "integer", "description": "Secondes (set_interval: intervalle global ; pl_set_interval: durée de cette page, 0=défaut)"},
                "enabled":  {"type": "boolean", "description": "set_schedule : activer/désactiver — TOUJOURS le renvoyer (reprendre l'état actuel si non modifié)"},
                "start":    {"type": "string",  "description": "set_schedule : début HH:MM"},
                "end":      {"type": "string",  "description": "set_schedule : fin HH:MM"},
                "days":     {"type": "array", "items": {"type": "integer"}, "description": "set_schedule : jours actifs (0=dimanche, 1=lundi … 6=samedi)"}
            },
            "required": ["action"]
        }
    }
]

_SYSTEM = """\
Tu es l'assistant vocal du kiosque d'affichage "wee rotate" (écran TV en rotation \
d'URLs dans un espace professionnel). Tu configures le kiosque à la place de \
l'utilisateur. Utilise toujours les outils AVANT de répondre, puis réponds en \
UNE phrase courte en français.

Règles :
- « Affiche X » = temporaire → open_url. « Ajoute X » / « mets X dans la playlist » = permanent → pl_add.
- URL d'un site que tu ne connais pas avec certitude → search_web d'abord. Ne devine jamais.
- Vidéo ou chaîne YouTube → search_youtube (recent=true pour « la dernière vidéo de… »).
- Pour viser une page existante (goto, pl_remove, pl_rename, pl_set_interval), utilise son index listé dans l'état ci-dessous.
- set_schedule : renvoie TOUJOURS enabled, start, end et days complets (reprends l'état actuel pour ce qui ne change pas).
- Afficher la date/heure → https://time.is/fr fonctionne bien en plein écran.
- Demande ambiguë ou impossible → réponds-le simplement, sans inventer.

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


_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
}


async def _fetch(url: str) -> str:
    from aiohttp import ClientSession, ClientTimeout
    async with ClientSession(timeout=ClientTimeout(total=12)) as sess:
        async with sess.get(url, headers=_HEADERS) as resp:
            return await resp.text(errors='replace')


def _parse_ddg(html: str) -> list:
    """Extrait [{title, url}] d'une page de résultats DuckDuckGo (html ou lite)."""
    results, seen = [], set()
    # Version html : <a class="result__a" href="...">Titre</a>
    for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        href  = m.group(1)
        title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        um  = re.search(r'uddg=([^&"]+)', href)
        url = urllib.parse.unquote(um.group(1)) if um else href
        if url.startswith('http') and 'duckduckgo.com' not in url and url not in seen:
            seen.add(url)
            results.append({'title': title, 'url': url})
        if len(results) >= 5:
            return results
    if results:
        return results
    # Fallback générique : tous les liens de redirection uddg= de la page
    for m in re.finditer(r'uddg=([^&"\']+)', html):
        url = urllib.parse.unquote(m.group(1))
        if url.startswith('http') and 'duckduckgo.com' not in url and url not in seen:
            seen.add(url)
            results.append({'title': '', 'url': url})
        if len(results) >= 5:
            break
    return results


async def search_web(query: str) -> dict:
    encoded = urllib.parse.quote_plus(query)
    for endpoint in (f'https://html.duckduckgo.com/html/?q={encoded}',
                     f'https://lite.duckduckgo.com/lite/?q={encoded}'):
        try:
            results = _parse_ddg(await _fetch(endpoint))
            if results:
                return {'ok': True, 'results': results}
        except Exception:
            continue
    return {'ok': False, 'error': 'Recherche web indisponible'}


async def search_youtube(query: str, recent: bool = False) -> dict:
    """YouTube search via page scraping (pas d'API key requise). Fallback sur yt-dlp."""
    sort_param = '&sp=CAI%3D' if recent else ''
    encoded = urllib.parse.quote_plus(query)
    try:
        html = await _fetch(f'https://www.youtube.com/results?search_query={encoded}{sort_param}')
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

    for _ in range(6):  # max 6 rounds d'outils
        resp = await _client.messages.create(
            model=_MODEL,
            max_tokens=700,
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
            if tu.name == 'search_web':
                result = await search_web(tu.input.get('query', ''))
                content = json.dumps(result, ensure_ascii=False)
            elif tu.name == 'search_youtube':
                result = await search_youtube(
                    tu.input.get('query', ''),
                    recent=bool(tu.input.get('recent', False)),
                )
                content = json.dumps(result)
            elif tu.name == 'kiosk_command':
                commands.append(dict(tu.input))
                content = '{"ok": true}'
            else:
                content = '{"ok": false, "error": "outil inconnu"}'
            tool_results.append({
                'type': 'tool_result',
                'tool_use_id': tu.id,
                'content': content,
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
    parts.append(f"Intervalle global : {s.get('interval', 30)} s")
    sch = s.get('schedule') or {}
    if sch.get('enabled'):
        parts.append(f"Horaires : {sch.get('start')}–{sch.get('end')}, jours {sch.get('days')}")
    else:
        parts.append('Horaires : désactivés (start '
                     + str(sch.get('start', '08:00')) + ', end ' + str(sch.get('end', '18:00'))
                     + ', days ' + str(sch.get('days', [1, 2, 3, 4, 5])) + ')')
    urls = s.get('urls', [])
    if urls:
        ci = s.get('currentIndex', 0)
        parts.append(f'Playlist ({len(urls)} pages) :')
        for i, u in enumerate(urls[:15]):
            nm  = u.get('name') or ''
            cur = '  ← affichée' if i == ci else ''
            dur = f" [{u.get('interval')}s]" if u.get('interval') else ''
            parts.append(f"  {i}. {nm + ' — ' if nm else ''}{u.get('url', '')}{dur}{cur}")
    else:
        parts.append('Playlist vide')
    return '\n'.join(parts)
