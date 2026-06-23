"""Source de démonstration : lit des e-mails d'exemple depuis un fichier JSON.

Permet de voir le rendu du tableau de bord sans aucun accès à une vraie boîte
mail. Les dates de réception sont calculées par rapport à « maintenant » pour
que les exemples tombent toujours dans la fenêtre de la nuit écoulée.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from ..models import RawEmail
from .base import MailSource

DEFAULT_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "sample_emails.json"


class DemoMailSource(MailSource):
    def __init__(self, fixtures_path: Optional[Path] = None):
        self.fixtures_path = fixtures_path or DEFAULT_FIXTURES

    def fetch_since(self, since: datetime) -> List[RawEmail]:
        data = json.loads(self.fixtures_path.read_text(encoding="utf-8"))
        now = datetime.now(timezone.utc)
        emails: List[RawEmail] = []
        for i, item in enumerate(data):
            if "day_offset" in item:
                # Position relative à minuit local : 0 = aujourd'hui, 1 = hier…
                midnight = now.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
                received = (
                    midnight
                    - timedelta(days=int(item["day_offset"]))
                    + timedelta(hours=float(item.get("hour", 3)))
                ).astimezone(timezone.utc)
            else:
                received = now - timedelta(hours=float(item.get("received_hours_ago", 8)))
            email = RawEmail(
                id=item.get("id", f"demo-{i}"),
                subject=item.get("subject", ""),
                sender_name=item.get("from_name", ""),
                sender_address=item.get("from_address", ""),
                received=received,
                body_text=item.get("body_text", ""),
                body_html=item.get("body_html", ""),
            )
            if email.received >= since:
                emails.append(email)
        return emails
