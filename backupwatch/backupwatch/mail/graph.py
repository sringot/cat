"""Source Microsoft Graph : lit une boîte Microsoft 365 / Outlook.

Authentification par « client credentials » (flux applicatif), idéale pour un
script qui tourne sans intervention chaque matin. Côté Azure AD il faut :

  1. Enregistrer une application (App registration).
  2. Lui accorder la permission APPLICATION `Mail.Read` (avec consentement admin).
  3. Créer un secret client.

Astuce sécurité : on peut restreindre l'app à une seule boîte via une
« Application Access Policy » Exchange Online, pour qu'elle ne lise que la boîte
dédiée aux rapports de sauvegarde.
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from typing import List
from urllib.parse import quote

from ..attachments import extract_attachment_text
from ..config import Config
from ..models import RawEmail
from ..textutils import html_to_text
from .base import MailSource

logger = logging.getLogger("backupwatch")

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
SCOPE = ["https://graph.microsoft.com/.default"]


class GraphMailSource(MailSource):
    def __init__(self, config: Config):
        config.validate_graph()
        self.config = config
        self._token: str | None = None

    # -- Authentification ---------------------------------------------------
    def _get_token(self) -> str:
        if self._token:
            return self._token
        import msal  # import différé

        app = msal.ConfidentialClientApplication(
            client_id=self.config.graph_client_id,
            authority=f"https://login.microsoftonline.com/{self.config.graph_tenant_id}",
            client_credential=self.config.graph_client_secret,
        )
        result = app.acquire_token_for_client(scopes=SCOPE)
        if "access_token" not in result:
            raise RuntimeError(
                "Échec de l'authentification Microsoft Graph : "
                f"{result.get('error')} — {result.get('error_description')}"
            )
        self._token = result["access_token"]
        return self._token

    # -- Récupération des messages -----------------------------------------
    def fetch_since(self, since: datetime) -> List[RawEmail]:
        import requests  # import différé

        token = self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            # Permet de trier/filtrer sur receivedDateTime sans erreur Graph.
            "Prefer": 'outlook.body-content-type="text"',
        }

        mailbox = quote(self.config.graph_mailbox)
        if self.config.graph_folder:
            folder = quote(self.config.graph_folder)
            base = f"{GRAPH_ROOT}/users/{mailbox}/mailFolders/{folder}/messages"
        else:
            base = f"{GRAPH_ROOT}/users/{mailbox}/messages"

        since_iso = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        params = {
            "$filter": f"receivedDateTime ge {since_iso}",
            "$orderby": "receivedDateTime desc",
            "$select": "id,subject,from,receivedDateTime,body,bodyPreview,hasAttachments",
            "$top": "50",
        }

        emails: List[RawEmail] = []
        url = base
        while url:
            resp = requests.get(url, headers=headers, params=params if url == base else None, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
            for msg in payload.get("value", []):
                email = self._to_raw_email(msg)
                # Acronis & co. mettent le résultat dans une PJ (ZIP → PDF) :
                # on en extrait le texte et on l'ajoute au corps pour le parser.
                if msg.get("hasAttachments"):
                    extra = self._attachments_text(base, msg.get("id"), headers)
                    if extra:
                        email.body_text = f"{email.body_text}\n{extra}".strip()
                emails.append(email)
            url = payload.get("@odata.nextLink")
        return emails

    def _attachments_text(self, base: str, message_id: str, headers: dict) -> str:
        import requests  # import différé

        # Pas de $select : `contentBytes` n'existe que sur le type dérivé
        # fileAttachment, et le sélectionner sur la collection renvoie une 400.
        # On récupère donc les pièces jointes complètes.
        url = f"{base}/{quote(message_id)}/attachments"
        texts: List[str] = []
        try:
            while url:
                resp = requests.get(url, headers=headers, timeout=30)
                resp.raise_for_status()
                payload = resp.json()
                for att in payload.get("value", []):
                    content_b64 = att.get("contentBytes")
                    if not content_b64:  # pièce jointe non-fichier (item/référence)
                        continue
                    try:
                        raw = base64.b64decode(content_b64)
                    except (ValueError, TypeError):
                        continue
                    text = extract_attachment_text(att.get("name", ""), raw)
                    if text:
                        texts.append(text)
                url = payload.get("@odata.nextLink")
        except Exception as exc:  # noqa: BLE001 - une PJ illisible ne doit pas tout casser
            logger.warning("Pièces jointes illisibles (msg %s…) : %s", message_id[:12], exc)
        return "\n".join(texts)

    @staticmethod
    def _to_raw_email(msg: dict) -> RawEmail:
        sender = (msg.get("from") or {}).get("emailAddress", {})
        body = msg.get("body") or {}
        content = body.get("content", "")
        content_type = (body.get("contentType") or "").lower()

        body_text = ""
        body_html = ""
        if content_type == "html":
            body_html = content
            body_text = html_to_text(content)
        else:
            body_text = content or msg.get("bodyPreview", "")

        received = datetime.fromisoformat(
            msg["receivedDateTime"].replace("Z", "+00:00")
        )
        return RawEmail(
            id=msg.get("id", ""),
            subject=msg.get("subject", "") or "",
            sender_name=sender.get("name", "") or "",
            sender_address=sender.get("address", "") or "",
            received=received,
            body_text=body_text,
            body_html=body_html,
        )
