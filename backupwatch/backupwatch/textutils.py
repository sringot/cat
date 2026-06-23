"""Petits utilitaires de texte (conversion HTML → texte)."""

from __future__ import annotations

import html
import re

try:  # BeautifulSoup donne un bien meilleur rendu, mais reste optionnel.
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_MULTINL_RE = re.compile(r"\n\s*\n\s*\n+")


def html_to_text(content: str) -> str:
    """Convertit un corps HTML en texte lisible.

    Utilise BeautifulSoup si disponible, sinon un repli par expressions
    régulières suffisant pour l'extraction de mots-clés.
    """
    if not content:
        return ""

    if BeautifulSoup is not None:
        soup = BeautifulSoup(content, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text("\n")
    else:  # pragma: no cover - repli sans dépendance
        text = _TAG_RE.sub(" ", content)
        text = html.unescape(text)

    text = _WS_RE.sub(" ", text)
    text = _MULTINL_RE.sub("\n\n", text)
    return text.strip()
