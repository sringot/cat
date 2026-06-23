"""Extraction de texte des pièces jointes (ZIP → PDF).

Certains logiciels (ex. Acronis) n'écrivent pas le résultat dans le corps du
mail mais dans un rapport PDF, souvent à l'intérieur d'un ZIP. Ce module
récupère ce texte pour que le parser puisse en déduire l'état du backup.
"""

from __future__ import annotations

import io
import logging
import zipfile

logger = logging.getLogger("backupwatch")

try:  # pypdf est requis pour lire les PDF ; absence gérée proprement.
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None


def _pdf_to_text(data: bytes) -> str:
    if PdfReader is None:  # pragma: no cover
        logger.warning("pypdf non installé : PDF ignoré (pip install pypdf).")
        return ""
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:  # noqa: BLE001 - un PDF illisible ne doit pas tout casser
        logger.warning("Lecture PDF échouée : %s", exc)
        return ""


def _zip_to_text(data: bytes, depth: int) -> str:
    parts = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                parts.append(extract_attachment_text(info.filename, archive.read(info), depth + 1))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Lecture ZIP échouée : %s", exc)
    return "\n".join(p for p in parts if p)


def extract_attachment_text(filename: str, data: bytes, depth: int = 0) -> str:
    """Texte extrait d'une pièce jointe PDF ou ZIP (récursif, profondeur bornée)."""
    if depth > 3 or not data:
        return ""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return _pdf_to_text(data)
    if name.endswith(".zip"):
        return _zip_to_text(data, depth)
    return ""
