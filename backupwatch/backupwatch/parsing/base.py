"""Interface des parsers et registre des parsers spécialisés.

Pour ajouter la prise en charge fine d'un logiciel précis (Veeam, Acronis…) :

  1. Créer une classe qui hérite de `BackupParser`.
  2. Implémenter `can_parse` (reconnaissance du format) et `parse` (extraction).
  3. Ajouter une instance à la liste `PARSERS` ci-dessous.

Tant que cette liste est vide, tout passe par le parser générique, qui sait
déjà déterminer succès / avertissement / échec pour la plupart des outils.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from ..models import BackupResult, RawEmail


class BackupParser(ABC):
    name: str = "base"

    @abstractmethod
    def can_parse(self, email: RawEmail) -> bool:
        """Renvoie True si ce parser sait traiter cet e-mail."""
        raise NotImplementedError

    @abstractmethod
    def parse(self, email: RawEmail) -> List[BackupResult]:
        """Extrait les résultats de sauvegarde de l'e-mail."""
        raise NotImplementedError


# Parsers spécialisés, essayés avant le générique. À compléter au besoin.
PARSERS: List[BackupParser] = []
