"""Tests de l'extraction de texte des pièces jointes (PDF et ZIP → PDF)."""

import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from backupwatch.attachments import extract_attachment_text
from backupwatch.models import BackupStatus, RawEmail
from backupwatch.parsing import parse_email

FIXTURE_PDF = Path(__file__).resolve().parents[1] / "fixtures" / "sample_acronis_report.pdf"


def _pdf_bytes() -> bytes:
    return FIXTURE_PDF.read_bytes()


def test_extract_text_from_pdf():
    text = extract_attachment_text("report.pdf", _pdf_bytes())
    assert "Succeeded" in text
    assert "Acronis" in text


def test_extract_text_from_zipped_pdf():
    # On emballe le PDF dans un ZIP, comme le fait Acronis.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Sauvegarde/report.pdf", _pdf_bytes())
    text = extract_attachment_text("backup.zip", buffer.getvalue())
    assert "Succeeded" in text


def test_unknown_attachment_type_is_ignored():
    assert extract_attachment_text("note.txt", b"peu importe") == ""


def test_parser_classifies_acronis_pdf_text():
    # Un mail Acronis vide, enrichi du texte du PDF, doit être classé "Succès".
    pdf_text = extract_attachment_text("report.pdf", _pdf_bytes())
    email = RawEmail(
        id="acronis-1",
        subject="Acronis Cyber Protect notification",
        sender_name="Acronis",
        sender_address="noreply@acronis.com",
        received=datetime.now(timezone.utc),
        body_text=pdf_text,
    )
    result = parse_email(email)[0]
    assert result.status is BackupStatus.SUCCESS
    assert result.source_tool == "Acronis"
