"""Modèles de données partagés dans toute l'application."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class BackupStatus(str, Enum):
    """État d'une sauvegarde, normalisé quel que soit le logiciel source."""

    SUCCESS = "success"
    WARNING = "warning"
    FAILED = "failed"
    UNKNOWN = "unknown"

    @property
    def label_fr(self) -> str:
        return {
            "success": "Succès",
            "warning": "Avertissement",
            "failed": "Échec",
            "unknown": "Inconnu",
        }[self.value]

    @property
    def severity(self) -> int:
        """Plus la valeur est élevée, plus c'est urgent (sert au tri du dashboard)."""
        return {"failed": 3, "warning": 2, "unknown": 1, "success": 0}[self.value]


@dataclass
class RawEmail:
    """Un e-mail brut récupéré de la boîte, indépendamment de la source."""

    id: str
    subject: str
    sender_name: str
    sender_address: str
    received: datetime
    body_text: str = ""
    body_html: str = ""


@dataclass
class BackupResult:
    """Résultat d'une sauvegarde extrait d'un e-mail."""

    client: str
    status: BackupStatus
    received: datetime
    job: Optional[str] = None
    source_tool: Optional[str] = None
    size: Optional[str] = None
    duration: Optional[str] = None
    detail: str = ""
    subject: str = ""
    email_id: str = ""
