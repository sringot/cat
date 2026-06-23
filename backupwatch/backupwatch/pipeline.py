"""Orchestration : récupérer → filtrer → parser → générer le tableau de bord."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

from .config import Config
from .mail import build_source
from .models import BackupResult, RawEmail
from .naming import apply_client_aliases
from .parsing import parse_email
from .report import build_dashboard

logger = logging.getLogger("backupwatch")


@dataclass
class RunResult:
    dashboard_path: Path
    results: List[BackupResult]
    emails_scanned: int
    emails_matched: int
    since: datetime


def _is_relevant(email: RawEmail, config: Config) -> bool:
    """Garde les mails de sauvegarde (expéditeur de confiance ou mot-clé présent)."""
    sender = (email.sender_address or "").lower()
    if config.trusted_senders and any(t.lower() in sender for t in config.trusted_senders):
        return True
    haystack = f"{email.subject}\n{email.body_text}\n{email.body_html}".lower()
    return any(keyword.lower() in haystack for keyword in config.keywords)


def run(config: Config) -> RunResult:
    """Exécute le cycle complet une fois et renvoie un récapitulatif."""
    source = build_source(config)

    # Fenêtre : 7 jours glissants (aujourd'hui + 6 jours) pour la vue hebdo,
    # élargie si lookback_hours dépasse cette durée.
    now = datetime.now(timezone.utc)
    start_week = (
        now.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        - timedelta(days=6)
    ).astimezone(timezone.utc)
    since = min(now - timedelta(hours=config.lookback_hours), start_week)

    emails = source.fetch_since(since)
    logger.info("%d e-mail(s) récupéré(s) depuis %s", len(emails), since.isoformat())

    matched = [e for e in emails if _is_relevant(e, config)]
    logger.info("%d e-mail(s) identifié(s) comme rapports de sauvegarde", len(matched))

    results: List[BackupResult] = []
    for email in matched:
        results.extend(parse_email(email))

    # Renomme les clients selon la table d'alias (PGE-NAS, NAS-HAVEN…).
    apply_client_aliases(results, config.client_aliases)

    dashboard_path = build_dashboard(results, config, since)
    logger.info("Tableau de bord généré : %s", dashboard_path)

    return RunResult(
        dashboard_path=dashboard_path,
        results=results,
        emails_scanned=len(emails),
        emails_matched=len(matched),
        since=since,
    )
