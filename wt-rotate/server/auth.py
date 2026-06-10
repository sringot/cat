"""
Token-based auth for mobile WebSocket clients.

A 16-char hex token is generated once and persisted to .wt_token so that
server restarts don't invalidate saved QR-code URLs. Delete the file to
rotate the token.
"""
import secrets
from pathlib import Path

_TOKEN_FILE = Path(__file__).parent.parent / '.wt_token'

def _init_token() -> str:
    if _TOKEN_FILE.exists():
        tok = _TOKEN_FILE.read_text().strip()
        if len(tok) >= 8:
            return tok
    tok = secrets.token_hex(8)
    try:
        _TOKEN_FILE.write_text(tok)
    except Exception:
        pass
    return tok

TOKEN: str = _init_token()

def validate(provided: str) -> bool:
    """Constant-time comparison to avoid timing attacks."""
    return secrets.compare_digest(provided or '', TOKEN)
