"""Renommage des clients via une table d'alias.

Chaque alias est un motif (recherché en insensible à la casse dans le sujet,
le client détecté et le logiciel) associé au nom à afficher. Le premier motif
qui correspond gagne — on place donc les plus spécifiques en premier.
"""

from __future__ import annotations

from typing import Dict, List

from .models import BackupResult


def apply_client_aliases(results: List[BackupResult], aliases: Dict[str, str]) -> None:
    """Remplace `client` par le nom d'alias correspondant (modification en place)."""
    if not aliases:
        return
    items = [(pattern.lower(), name) for pattern, name in aliases.items()]
    for result in results:
        haystack = f"{result.subject} {result.client} {result.source_tool or ''}".lower()
        for pattern, name in items:
            if pattern and pattern in haystack:
                result.client = name
                break
