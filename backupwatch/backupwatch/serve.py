"""Mode serveur — affichage permanent en kiosque.

Sert le dernier tableau de bord sur une URL fixe (``http://host:port/``) et
relance le scraping automatiquement chaque matin à heure fixe. Pensé pour un
écran de kiosque : on lance le programme une fois, l'URL ne bouge plus, et la
page (qui s'auto-rafraîchit déjà via le gabarit) montre les données du jour
sans aucune intervention.

Uniquement de la bibliothèque standard : aucun serveur web tiers requis.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from .config import Config
from .pipeline import run

logger = logging.getLogger("backupwatch")

# Page affichée tant que le tout premier rapport n'est pas encore généré.
# Se recharge toute seule toutes les 15 s pour laisser place au dashboard réel.
_PLACEHOLDER = (
    '<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
    '<meta http-equiv="refresh" content="15"><title>BackupWatch</title>'
    '<style>html,body{height:100%;margin:0}body{display:flex;align-items:center;'
    'justify-content:center;font-family:system-ui,-apple-system,sans-serif;'
    'background:#eef0fa;color:#3b4063}div{text-align:center}'
    'h1{font-weight:600;letter-spacing:-.02em}p{color:#a6acc6}</style></head>'
    '<body><div><h1>BackupWatch</h1>'
    '<p>Premier rapport en cours de génération…</p></div></body></html>'
).encode("utf-8")


def next_run(now: datetime, hour: int) -> datetime:
    """Prochaine occurrence de ``hour:00`` : aujourd'hui si pas encore passée, sinon demain."""
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


class Dashboard:
    """Cache thread-safe du dernier HTML servi.

    Le scraping (thread planificateur) écrit ici, le serveur HTTP lit ici : on
    ne sert jamais un fichier en cours de réécriture, et un scraping en échec
    laisse simplement le dernier bon tableau de bord en place.
    """

    def __init__(self, html: bytes = _PLACEHOLDER) -> None:
        self._lock = threading.Lock()
        self._html = html
        self.generated_at: Optional[datetime] = None

    def set_html(self, html: bytes) -> None:
        with self._lock:
            self._html = html
            self.generated_at = datetime.now()

    def get_html(self) -> bytes:
        with self._lock:
            return self._html


def make_handler(dash: Dashboard):
    """Fabrique un handler HTTP qui sert toujours le dernier dashboard en cache."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - signature imposée par BaseHTTPRequestHandler
            if self.path.startswith("/healthz"):
                ts = dash.generated_at.isoformat() if dash.generated_at else "null"
                self._send(200, f'{{"ok":true,"generated_at":"{ts}"}}'.encode(),
                           "application/json")
                return
            if self.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            self._send(200, dash.get_html(), "text/html; charset=utf-8")

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # client parti (onglet rechargé) — sans gravité

        def log_message(self, *args) -> None:
            pass  # silence les logs d'accès par requête

    return Handler


def scrape_once(config: Config, dash: Dashboard) -> bool:
    """Lance le pipeline et met à jour le cache. En cas d'échec, garde l'ancien HTML.

    Renvoie True si le tableau de bord a été régénéré.
    """
    try:
        result = run(config)
        dash.set_html(Path(result.dashboard_path).read_bytes())
        logger.info("Tableau de bord rafraîchi (%d rapport(s))", len(result.results))
        return True
    except Exception:  # noqa: BLE001 - le serveur ne doit jamais tomber sur une erreur de scraping
        logger.exception("Échec du scraping — l'ancien tableau de bord reste affiché")
        return False


def _scheduler(config: Config, dash: Dashboard, hour: int, stop: threading.Event) -> None:
    # Rafraîchit tout de suite au démarrage pour ne pas rester sur le placeholder.
    scrape_once(config, dash)
    while not stop.is_set():
        target = next_run(datetime.now(), hour)
        wait = (target - datetime.now()).total_seconds()
        logger.info("Prochain scraping : %s (dans %.0f min)",
                    target.strftime("%d/%m %H:%M"), wait / 60)
        if stop.wait(wait):  # réveillé avant l'heure = demande d'arrêt
            break
        scrape_once(config, dash)


def serve(config: Config, host: str = "127.0.0.1", port: int = 8470, hour: int = 7) -> int:
    """Démarre le serveur du tableau de bord et le planificateur quotidien."""
    dash = Dashboard()

    # Affiche immédiatement le dernier dashboard sur disque s'il en existe un,
    # le temps que le premier scraping du démarrage se termine.
    existing = Path(config.dashboard_path)
    if existing.exists():
        dash.set_html(existing.read_bytes())

    stop = threading.Event()
    scheduler = threading.Thread(
        target=_scheduler, args=(config, dash, hour, stop), daemon=True
    )
    scheduler.start()

    httpd = ThreadingHTTPServer((host, port), make_handler(dash))
    shown = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
    print(f"BackupWatch — tableau de bord servi sur http://{shown}:{port}/")
    print(f"Scraping automatique chaque jour à {hour:02d}:00. Ctrl+C pour arrêter.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt…")
    finally:
        stop.set()
        httpd.shutdown()
        httpd.server_close()
    return 0
