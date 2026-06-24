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

# Garde-fous mémoire pour le petit NUC (gros PDF, ZIP-bomb).
_MAX_PDF_PAGES = 60
_MAX_ENTRY_BYTES = 25 * 1024 * 1024  # 25 Mo par entrée de ZIP décompressée


def _pdf_to_text(data: bytes) -> str:
    if PdfReader is None:  # pragma: no cover
        logger.warning("pypdf non installé : PDF ignoré (pip install pypdf).")
        return ""
    try:
        reader = PdfReader(io.BytesIO(data))
        parts = []
        for i, page in enumerate(reader.pages):
            if i >= _MAX_PDF_PAGES:
                logger.info("PDF tronqué à %d pages.", _MAX_PDF_PAGES)
                break
            parts.append(page.extract_text() or "")
        return "\n".join(parts)
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
                if info.file_size > _MAX_ENTRY_BYTES:  # anti ZIP-bomb / pièce énorme
                    logger.warning("Entrée ZIP %s ignorée (%d octets).",
                                   info.filename, info.file_size)
                    continue
                try:
                    raw = archive.read(info)
                except Exception as exc:  # noqa: BLE001 - une entrée corrompue n'empêche pas les autres
                    logger.warning("Entrée ZIP %s illisible : %s", info.filename, exc)
                    continue
                parts.append(extract_attachment_text(info.filename, raw, depth + 1))
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
