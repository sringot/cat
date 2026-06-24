"""Tests du rendu : réconciliation des compteurs (les inconnus comptent)."""

from datetime import datetime, timezone

from backupwatch.config import Config
from backupwatch.models import BackupResult, BackupStatus
from backupwatch.report.dashboard import build_dashboard


def _res(status):
    return BackupResult(client="c", status=status, received=datetime.now(timezone.utc))


def test_unknown_gets_its_own_tile(tmp_path):
    # 1 succès + 2 inconnus : les inconnus comptent dans le total ET ont leur
    # tuile, pour que les tuiles s'additionnent au total annoncé.
    results = [_res(BackupStatus.SUCCESS), _res(BackupStatus.UNKNOWN), _res(BackupStatus.UNKNOWN)]
    config = Config(mail_source="demo", output_dir=tmp_path)
    html = build_dashboard(results, config).decode("utf-8")
    assert "Inconnus" in html
    assert "3 sauvegardes analysées" in html


def test_no_unknown_tile_when_zero(tmp_path):
    results = [_res(BackupStatus.SUCCESS)]
    config = Config(mail_source="demo", output_dir=tmp_path)
    html = build_dashboard(results, config).decode("utf-8")
    assert "Inconnus" not in html


def test_build_dashboard_returns_html_bytes(tmp_path):
    # build_dashboard renvoie les octets rendus (utilisés directement par le
    # serveur) en plus d'écrire le fichier.
    config = Config(mail_source="demo", output_dir=tmp_path)
    html = build_dashboard([_res(BackupStatus.SUCCESS)], config)
    assert isinstance(html, bytes)
    assert html == (tmp_path / "dashboard.html").read_bytes()
