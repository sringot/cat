from typing import Optional, Set

PORT: int = 8765

# Shared mutable server state (asyncio single-threaded — no locking needed)
ext_ws = None          # WebSocketResponse | None
ext_takeovers: list = []   # horodatages des évictions (détection doublon)
mob_clients: Set = set()
cached_state: dict = {}
local_ip: str = '127.0.0.1'
qr_cache: Optional[bytes] = None
html_cache: Optional[bytes] = None
guide_cache: Optional[bytes] = None
manifest_cache: Optional[bytes] = None
icon_cache: dict = {}
