"""Renommage des clients via une table d'alias.

Chaque alias est un motif (recherché en insensible à la casse dans le sujet,
le client détecté et le logiciel) associé au nom à afficher. Le premier motif
qui correspond gagne — on place donc les plus spécifiques en premier.
"""

from __future__ import annotations

import re
from typing import Dict, List

from .models import BackupResult


def _matches(pattern: str, haystack: str) -> bool:
    """Vrai si `pattern` apparaît comme un terme entier (frontières de mot).

    Évite qu'un alias court morde dans un mot plus long : « sql » ne doit pas
    matcher dans « postgresql », ni « hp » dans « sharepoint ».
    """
    return re.search(r"(?<!\w)" + re.escape(pattern) + r"(?!\w)", haystack) is not None


def apply_client_aliases(results: List[BackupResult], aliases: Dict[str, str]) -> None:
    """Remplace `client` par le nom d'alias correspondant (modification en place)."""
    if not aliases:
        return
    items = [(pattern.lower(), name) for pattern, name in aliases.items()]
    for result in results:
        haystack = f"{result.subject} {result.client} {result.source_tool or ''}".lower()
        for pattern, name in items:
            if pattern and _matches(pattern, haystack):
                result.client = name
                break
