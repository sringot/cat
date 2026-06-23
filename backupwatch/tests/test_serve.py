"""Tests du mode serveur : planification, cache thread-safe et service HTTP."""

import threading
import urllib.request
from datetime import datetime
from http.server import ThreadingHTTPServer

from backupwatch.config import Config
from backupwatch.serve import Dashboard, make_handler, next_run, scrape_once


# ── Planification : prochaine occurrence de hh:00 ────────────────────────────

def test_next_run_today_when_hour_not_passed():
    now = datetime(2026, 6, 23, 6, 30)
    assert next_run(now, 7) == datetime(2026, 6, 23, 7, 0)


def test_next_run_tomorrow_when_hour_passed():
    now = datetime(2026, 6, 23, 8, 15)
    assert next_run(now, 7) == datetime(2026, 6, 24, 7, 0)


def test_next_run_tomorrow_when_exactly_on_hour():
    # À 7h00 pile, le scraping du jour est considéré fait → on vise demain.
    now = datetime(2026, 6, 23, 7, 0, 0)
    assert next_run(now, 7) == datetime(2026, 6, 24, 7, 0)


# ── Cache HTML thread-safe ───────────────────────────────────────────────────

def test_dashboard_starts_on_placeholder():
    dash = Dashboard()
    assert b"Premier rapport" in dash.get_html()
    assert dash.generated_at is None


def test_dashboard_set_and_get():
    dash = Dashboard()
    dash.set_html(b"<html>ok</html>")
    assert dash.get_html() == b"<html>ok</html>"
    assert dash.generated_at is not None


def test_scrape_once_demo_updates_cache(tmp_path):
    dash = Dashboard()
    config = Config(mail_source="demo", lookback_hours=24, output_dir=tmp_path)
    assert scrape_once(config, dash) is True
    html = dash.get_html().decode("utf-8")
    assert "BackupWatch" in html
    assert (tmp_path / "dashboard.html").exists()


def test_scrape_once_keeps_last_html_on_failure(tmp_path):
    dash = Dashboard()
    dash.set_html(b"<html>ancien</html>")
    # Source inconnue → build_source lève → le pipeline échoue proprement.
    config = Config(mail_source="inexistante", output_dir=tmp_path)
    assert scrape_once(config, dash) is False
    assert dash.get_html() == b"<html>ancien</html>"  # inchangé


# ── Service HTTP ─────────────────────────────────────────────────────────────

def _serve_in_thread(dash):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(dash))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as resp:
        return resp.status, resp.read(), resp.headers


def test_http_serves_current_dashboard():
    dash = Dashboard()
    dash.set_html(b"<html>dashboard du jour</html>")
    httpd, port = _serve_in_thread(dash)
    try:
        status, body, headers = _get(port, "/")
        assert status == 200
        assert body == b"<html>dashboard du jour</html>"
        assert headers["Cache-Control"] == "no-store"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_http_reflects_cache_update_live():
    # Le serveur sert toujours le dernier HTML : une régénération est vue sans relancer.
    dash = Dashboard()
    dash.set_html(b"avant")
    httpd, port = _serve_in_thread(dash)
    try:
        assert _get(port, "/")[1] == b"avant"
        dash.set_html(b"apres")
        assert _get(port, "/")[1] == b"apres"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_http_healthz_and_favicon():
    dash = Dashboard()
    httpd, port = _serve_in_thread(dash)
    try:
        status, body, _ = _get(port, "/healthz")
        assert status == 200
        assert b'"ok":true' in body
        assert _get(port, "/favicon.ico")[0] == 204
    finally:
        httpd.shutdown()
        httpd.server_close()
