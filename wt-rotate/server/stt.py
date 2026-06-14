"""
Transcription vocale (speech-to-text) via l'API Groq — Whisper large-v3.
Gratuit, rapide, compatible OpenAI.

Clé : variable d'environnement GROQ_API_KEY (remplie par start_remote.bat
depuis le fichier cle_groq.txt). Sans clé, le micro vocal est désactivé mais
le reste fonctionne (l'assistant reste pilotable au texte).
"""
import os

_key   = ''
_URL   = 'https://api.groq.com/openai/v1/audio/transcriptions'
_MODEL = 'whisper-large-v3'

# Extension de fichier déduite du type MIME envoyé par le navigateur
_EXT = {
    'audio/webm': 'webm', 'audio/ogg': 'ogg',  'audio/mp4': 'mp4',
    'audio/mpeg': 'mp3',  'audio/wav': 'wav',   'audio/x-m4a': 'm4a',
    'audio/aac':  'aac',  'audio/mp3': 'mp3',
}


def init() -> None:
    global _key
    _key = os.environ.get('GROQ_API_KEY', '').strip()
    if _key:
        print(f'[STT] Transcription vocale active (Groq {_MODEL})')


def is_available() -> bool:
    return bool(_key)


async def transcribe(audio: bytes, mime: str) -> str:
    """Transcrit l'audio en texte (français). Chaîne vide si échec."""
    if not _key or not audio:
        return ''
    ext = _EXT.get((mime or '').split(';')[0].strip(), 'webm')
    from aiohttp import ClientSession, ClientTimeout, FormData
    form = FormData()
    form.add_field('file', audio, filename=f'audio.{ext}',
                   content_type=(mime or 'application/octet-stream'))
    form.add_field('model', _MODEL)
    form.add_field('language', 'fr')
    form.add_field('response_format', 'json')
    try:
        async with ClientSession(timeout=ClientTimeout(total=30)) as sess:
            async with sess.post(
                _URL, data=form,
                headers={'Authorization': f'Bearer {_key}'},
            ) as resp:
                if resp.status != 200:
                    return ''
                data = await resp.json()
                return (data.get('text') or '').strip()
    except Exception:
        return ''
