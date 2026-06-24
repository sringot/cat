"""Tests du parser générique : détection d'état, extraction, anti-faux-positifs."""

from datetime import datetime, timezone

from backupwatch.models import BackupStatus, RawEmail
from backupwatch.parsing import parse_email


def _email(subject="", body_text="", body_html="", sender_name="", sender_address=""):
    return RawEmail(
        id="t",
        subject=subject,
        sender_name=sender_name,
        sender_address=sender_address,
        received=datetime.now(timezone.utc),
        body_text=body_text,
        body_html=body_html,
    )


def test_success_in_subject():
    res = parse_email(_email(subject="Job 'Daily' finished with Success"))[0]
    assert res.status is BackupStatus.SUCCESS
    assert res.job == "Daily"


def test_failure_detected():
    res = parse_email(
        _email(subject="Backup failed", body_text="Error: cannot reach host")
    )[0]
    assert res.status is BackupStatus.FAILED
    assert "Error" in res.detail


def test_warning_beats_success():
    res = parse_email(_email(subject="Backup completed with warnings"))[0]
    assert res.status is BackupStatus.WARNING


def test_failure_in_body_beats_success_in_subject():
    # Cas dangereux : sujet « terminé » neutre, échec réel dans le corps.
    # L'échec doit primer — sinon une sauvegarde en échec s'afficherait en vert.
    res = parse_email(
        _email(subject="Sauvegarde terminée",
               body_text="La tâche a échoué : 3 erreurs détectées.")
    )[0]
    assert res.status is BackupStatus.FAILED


def test_german_failure():
    res = parse_email(
        _email(subject="Sicherung", body_text="Die Sicherung ist fehlgeschlagen.")
    )[0]
    assert res.status is BackupStatus.FAILED


def test_success_completed_zero_files():
    # « completed 0 files » reste un succès : la négation « 0 » ne vaut que
    # pour les termes de problème (« Errors: 0 »), pas pour les mots de succès.
    res = parse_email(_email(subject="Backup completed 0 files copied"))[0]
    assert res.status is BackupStatus.SUCCESS


def test_zero_errors_is_not_a_failure():
    # « Errors: 0 » et « 0 warnings » ne doivent pas déclencher d'échec.
    res = parse_email(
        _email(subject="Backup completed", body_text="Errors: 0\nWarnings: 0")
    )[0]
    assert res.status is BackupStatus.SUCCESS


def test_french_success():
    res = parse_email(
        _email(subject="Sauvegarde terminée", body_text="La sauvegarde s'est terminée avec succès. Aucune erreur.")
    )[0]
    assert res.status is BackupStatus.SUCCESS


def test_french_failure_verb_echoue():
    # Cas réel Synology : « La tâche ... a échoué » doit être un ÉCHEC, pas Inconnu.
    res = parse_email(
        _email(subject="[hawaii-syno] Network backup - La tâche Synology NAS 1 a échoué")
    )[0]
    assert res.status is BackupStatus.FAILED


def test_unknown_when_no_status():
    res = parse_email(_email(subject="Rapport de sauvegarde", body_text="Voir pièce jointe."))[0]
    assert res.status is BackupStatus.UNKNOWN


def test_client_from_bracket_tag():
    res = parse_email(_email(subject="[ACME Corp] Veeam Job 'X' Success"))[0]
    assert res.client == "ACME Corp"


def test_source_tool_detection():
    res = parse_email(_email(subject="Veeam Backup report", body_text="Result: Success"))[0]
    assert res.source_tool == "Veeam"


def test_size_and_duration_extraction():
    res = parse_email(
        _email(
            subject="Backup done with Success",
            body_text="Total size: 480.5 GB\nDuration: 01:42:10",
        )
    )[0]
    assert res.size == "480.5 GB"
    assert res.duration == "01:42:10"
