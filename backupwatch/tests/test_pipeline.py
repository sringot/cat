"""Test de bout en bout du pipeline en mode démo (vue hebdomadaire)."""

from collections import Counter

from backupwatch.config import Config
from backupwatch.models import BackupStatus
from backupwatch.pipeline import run


def test_demo_pipeline_generates_dashboard(tmp_path):
    config = Config(mail_source="demo", lookback_hours=24, output_dir=tmp_path)
    result = run(config)

    # 25 e-mails d'exemple ; la newsletter est filtrée → 24 rapports.
    assert result.emails_scanned == 25
    assert result.emails_matched == 24
    assert len(result.results) == 24

    counts = Counter(r.status for r in result.results)
    assert counts[BackupStatus.FAILED] == 2
    assert counts[BackupStatus.WARNING] == 2
    assert counts[BackupStatus.SUCCESS] == 20
    assert counts[BackupStatus.UNKNOWN] == 0

    # Le dashboard doit exister et contenir les sections clés.
    assert result.dashboard_path.exists()
    html = result.dashboard_path.read_text(encoding="utf-8")
    assert "BackupWatch" in html
    assert "Supervision des sauvegardes" in html
    assert "Par logiciel" in html
    assert "Statistiques" in html
    assert "hawaii-syno" in html  # dernier échec (carte Top)
