#!/usr/bin/env python3
"""
canva_server.py — sert l'image Canva en local sur http://localhost:8080/canva.png

Deux modes :
  1. Manuel : tu exportes le PNG depuis Canva, tu le déposes dans ce dossier sous
     le nom "canva.png". Le serveur le sert immédiatement.
  2. Auto   : remplis CANVA_PUBLIC_URL avec le lien public du design (Partager →
     "Tout le monde peut afficher"). Le script récupère automatiquement l'aperçu
     toutes les heures.

Lancer : python canva_server.py
URL à mettre dans wt-rotate : http://localhost:8080/canva.png
"""
import http.server, threading, time, os, re, urllib.request, sys

# ═══════════════════════════════════════════════════════════════════
#  CONFIG  ← modifie uniquement cette section
# ═══════════════════════════════════════════════════════════════════
CANVA_PUBLIC_URL = ""      # lien public Canva, ou "" pour mode manuel
PORT             = 8080
REFRESH_SECONDS  = 3600    # intervalle de re-téléchargement (1h)
# ═══════════════════════════════════════════════════════════════════

HERE       = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(HERE, "canva.png")
STAMP_FILE = os.path.join(HERE, ".last_fetch")


def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def fetch_from_canva():
    """Télécharge l'og:image du lien public Canva."""
    if not CANVA_PUBLIC_URL:
        return False
    try:
        req = urllib.request.Request(
            CANVA_PUBLIC_URL,
            headers={"User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )}
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", errors="ignore")

        # og:image peut apparaître dans deux ordres d'attributs
        patterns = [
            r'property=["\']og:image["\'][^>]+content=["\'](https://[^"\'?]+)',
            r'content=["\'](https://[^"\'?]+)[^>]+property=["\']og:image["\']',
        ]
        img_url = None
        for p in patterns:
            m = re.search(p, html)
            if m:
                img_url = m.group(1)
                break

        if not img_url:
            log("og:image introuvable — design probablement privé ou URL incorrecte")
            return False

        log(f"Téléchargement image Canva…")
        tmp = CACHE_FILE + ".tmp"
        urllib.request.urlretrieve(img_url, tmp)
        os.replace(tmp, CACHE_FILE)
        with open(STAMP_FILE, "w") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
        log(f"Image mise à jour ({os.path.getsize(CACHE_FILE)//1024} Ko)")
        return True

    except Exception as e:
        log(f"Erreur fetch Canva : {e}")
        return False


def refresh_loop():
    while True:
        fetch_from_canva()
        time.sleep(REFRESH_SECONDS)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/canva.png", "/canva.jpg", "/canva.jpeg"):
            # Cherche le fichier (png, jpg, jpeg)
            candidates = ["canva.png", "canva.jpg", "canva.jpeg"]
            found = None
            for name in candidates:
                fp = os.path.join(HERE, name)
                if os.path.exists(fp):
                    found = fp
                    break

            if found:
                ctype = "image/png" if found.endswith(".png") else "image/jpeg"
                with open(found, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-cache, no-store")
                self.end_headers()
                self.wfile.write(data)
            else:
                msg = b"Image pas encore disponible.\nDépose canva.png dans le dossier du script."
                self.send_response(503)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass  # silence les logs HTTP dans la console


if __name__ == "__main__":
    log(f"=== canva_server démarré sur http://localhost:{PORT}/canva.png ===")

    if CANVA_PUBLIC_URL:
        log(f"Mode auto — URL Canva : {CANVA_PUBLIC_URL[:60]}…")
        t = threading.Thread(target=refresh_loop, daemon=True)
        t.start()
    else:
        log("Mode manuel — dépose canva.png dans ce dossier pour mettre à jour l'image")
        if os.path.exists(CACHE_FILE):
            log(f"Image actuelle : {os.path.getsize(CACHE_FILE)//1024} Ko")
        else:
            log("Aucune image trouvée pour l'instant")

    try:
        with http.server.HTTPServer(("127.0.0.1", PORT), Handler) as httpd:
            log("Serveur prêt. Ctrl+C pour arrêter.")
            httpd.serve_forever()
    except KeyboardInterrupt:
        log("Arrêt.")
    except OSError as e:
        log(f"ERREUR : {e}")
        log(f"Le port {PORT} est peut-être déjà utilisé. Modifie PORT dans le script.")
        sys.exit(1)
