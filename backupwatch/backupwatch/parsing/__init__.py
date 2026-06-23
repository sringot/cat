"""Parsing des e-mails de sauvegarde.

`parse_email` essaie chaque parser enregistré dans l'ordre, et retombe sur le
parser générique si aucun parser spécialisé ne reconnaît le message.
"""

from __future__ import annotations

from typing import List

from ..models import BackupResult, RawEmail
from .base import PARSERS
from .generic import GenericParser

_GENERIC = GenericParser()


def parse_email(email: RawEmail) -> List[BackupResult]:
    """Extrait un ou plusieurs résultats de sauvegarde d'un e-mail."""
    for parser in PARSERS:
        if parser.can_parse(email):
            results = parser.parse(email)
            if results:
                return results
    return _GENERIC.parse(email)


__all__ = ["parse_email", "GenericParser", "PARSERS"]
