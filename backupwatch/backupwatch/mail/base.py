"""Interface commune à toutes les sources d'e-mails."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List

from ..models import RawEmail


class MailSource(ABC):
    """Source d'e-mails : sait renvoyer les messages reçus depuis une date."""

    @abstractmethod
    def fetch_since(self, since: datetime) -> List[RawEmail]:
        """Renvoie les e-mails reçus à partir de `since` (datetime aware, UTC)."""
        raise NotImplementedError
