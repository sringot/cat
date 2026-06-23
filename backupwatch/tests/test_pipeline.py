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

    # Le dashboard doit exister et contenir les éléments clés du board de supervision.
    assert result.dashboard_path.exists()
    html = result.dashboard_path.read_text(encoding="utf-8")
    assert "BackupWatch" in html
    # Bandeau d'état glançable : une sauvegarde a échoué cette nuit (jeu démo).
    assert 'class="status status--fail"' in html
    # Les trois compteurs.
    assert "Succès" in html and "Avertissements" in html and "Échecs" in html
    # La liste « à vérifier » nomme le client en échec.
    assert "À vérifier" in html
    assert "hawaii-syno" in html
    # Aucune dépendance externe : le board doit s'afficher hors-ligne.
    assert "jsdelivr" not in html and "googleapis" not in html
    # Police Inter embarquée (woff2 base64), pas de police distante.
    assert "data:font/woff2;base64," in html
