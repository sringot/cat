"""
Push notification support via Web Push (VAPID).
Requires:  pip install pywebpush
Falls back gracefully if pywebpush is not installed.
"""
import json, base64, asyncio, logging
from pathlib import Path

_subs_lock = asyncio.Lock()
log = logging.getLogger(__name__)

_KEY_FILE  = Path(__file__).parent.parent / '.wt_vapid'
_SUBS_FILE = Path(__file__).parent.parent / '.wt_push_subs.json'

VAPID_PUBLIC    = ''
VAPID_PRIVATE   = ''
VAPID_AVAILABLE = False

def _init():
    global VAPID_PUBLIC, VAPID_PRIVATE, VAPID_AVAILABLE
    try:
        from cryptography.hazmat.primitives.asymmetric.ec import generate_private_key, SECP256R1
        from cryptography.hazmat.primitives import serialization
    except ImportError:
        return  # cryptography not available

    if _KEY_FILE.exists():
        try:
            d = json.loads(_KEY_FILE.read_text())
            VAPID_PRIVATE = d['private_key']
            VAPID_PUBLIC  = d['public_key']
            VAPID_AVAILABLE = True
            return
        except Exception:
            pass

    # Generate a fresh key pair
    try:
        priv = generate_private_key(SECP256R1())
        pub  = priv.public_key()
        priv_pem = priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ).decode()
        pub_bytes = pub.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )
        pub_b64 = base64.urlsafe_b64encode(pub_bytes).rstrip(b'=').decode()
        _KEY_FILE.write_text(json.dumps({'private_key': priv_pem, 'public_key': pub_b64}))
        VAPID_PRIVATE = priv_pem
        VAPID_PUBLIC  = pub_b64
        VAPID_AVAILABLE = True
    except Exception:
        pass

_init()


def _load_subs() -> list:
    try:
        return json.loads(_SUBS_FILE.read_text())
    except Exception:
        return []

def _save_subs(subs: list):
    try:
        _SUBS_FILE.write_text(json.dumps(subs))
    except Exception:
        pass

async def save_subscription(sub: dict):
    if not sub.get('endpoint') or not isinstance(sub.get('endpoint'), str):
        return
    try:
        if len(json.dumps(sub)) > 4096:
            return
    except Exception:
        return
    async with _subs_lock:
        subs = _load_subs()
        subs = [s for s in subs if s.get('endpoint') != sub['endpoint']]
        subs.append(sub)
        _save_subs(subs)

async def remove_subscription(endpoint: str):
    """Remove a subscription by endpoint URL (called on client unsubscribe)."""
    if not endpoint:
        return
    async with _subs_lock:
        subs = _load_subs()
        subs = [s for s in subs if s.get('endpoint') != endpoint]
        _save_subs(subs)

def _send_one(sub: dict, title: str, body: str) -> bool:
    """Returns True on success, False on error, 'expired' if 410 Gone."""
    try:
        from pywebpush import webpush, WebPushException
        webpush(
            subscription_info={
                'endpoint': sub['endpoint'],
                'keys': sub.get('keys', {})
            },
            data=json.dumps({'title': title, 'body': body}),
            vapid_private_key=VAPID_PRIVATE,
            vapid_claims={'sub': 'mailto:admin@wt-rotate.local'},
            ttl=3600
        )
        return True
    except Exception as e:
        status = getattr(getattr(e, 'response', None), 'status_code', None)
        if status == 410:
            return 'expired'
        log.warning('Push delivery failed: %s', e)
        return False

async def notify(title: str, body: str):
    """Send push notification to all subscribers (runs in thread pool to avoid blocking)."""
    if not VAPID_AVAILABLE:
        return
    async with _subs_lock:
        subs = _load_subs()
        if not subs:
            return
        loop = asyncio.get_running_loop()
        to_remove = []
        for sub in subs:
            result = await loop.run_in_executor(None, _send_one, sub, title, body)
            if result == 'expired':
                to_remove.append(sub['endpoint'])
        if to_remove:
            subs = [s for s in subs if s.get('endpoint') not in to_remove]
            _save_subs(subs)
