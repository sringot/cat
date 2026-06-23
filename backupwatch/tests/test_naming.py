"""Tests du renommage des clients via la table d'alias."""

from datetime import datetime, timezone

from backupwatch.models import BackupResult, BackupStatus
from backupwatch.naming import apply_client_aliases


def _result(subject="", client="", source_tool=None):
    return BackupResult(
        client=client,
        status=BackupStatus.SUCCESS,
        received=datetime.now(timezone.utc),
        subject=subject,
        source_tool=source_tool,
    )


def test_alias_matches_subject():
    aliases = {"pge-nas": "PGE-NAS", "nas-mfip": "NAS-MFIP"}
    results = [
        _result(subject="PGE-NAS La tâche Network backup a été effectuée", client="serveur"),
        _result(subject="[nas-mfip.fr1.quickconnect.to] Réplication_MFIP", client="nas-mfip..."),
    ]
    apply_client_aliases(results, aliases)
    assert results[0].client == "PGE-NAS"
    assert results[1].client == "NAS-MFIP"


def test_alias_matches_source_tool():
    # Le sujet Acronis ne contient pas "acronis" ; on s'appuie sur le logiciel détecté.
    results = [_result(subject="RAPPORT QUOTIDIEN SUR 16 juin 2026", client="?", source_tool="Acronis")]
    apply_client_aliases(results, {"acronis": "ACRONIS"})
    assert results[0].client == "ACRONIS"


def test_no_alias_leaves_client_untouched():
    results = [_result(subject="autre chose", client="Original")]
    apply_client_aliases(results, {"pge-nas": "PGE-NAS"})
    assert results[0].client == "Original"


def test_empty_aliases_is_noop():
    results = [_result(subject="PGE-NAS", client="x")]
    apply_client_aliases(results, {})
    assert results[0].client == "x"
