from typing import Optional, Set

PORT: int = 8765
HTTPS_PORT: int = 8766   # micro vocal : getUserMedia exige un contexte sécurisé

# Shared mutable server state (asyncio single-threaded — no locking needed)
ext_ws = None          # WebSocketResponse | None
ext_takeovers: list = []   # horodatages des évictions (détection doublon)
mob_clients: Set = set()
cached_state: dict = {}
cached_shot: Optional[str] = None   # dernier screenshot (JSON brut) pour les mobiles qui arrivent
cached_shot_ts: float = 0.0
local_ip: str = '127.0.0.1'
https_on: bool = False   # serveur HTTPS effectivement démarré (certificat OK)
qr_cache: Optional[bytes] = None
html_cache: Optional[bytes] = None
guide_cache: Optional[bytes] = None
manifest_cache: Optional[bytes] = None
icon_cache: dict = {}
