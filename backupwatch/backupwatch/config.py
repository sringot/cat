"""Chargement de la configuration.

- Les réglages de comportement (mots-clés, expéditeurs de confiance, fenêtre de
  temps, sortie) viennent d'un fichier `config.yaml` optionnel.
- Les secrets (identifiants Microsoft Graph) viennent des variables
  d'environnement, éventuellement chargées depuis un fichier `.env`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# python-dotenv est optionnel : s'il est absent, on lit quand même l'environnement.
try:  # pragma: no cover - dépend de l'environnement
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

# PyYAML est optionnel : sans lui, on se contente des valeurs par défaut + env.
try:  # pragma: no cover
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


# Mots-clés qui permettent de repérer un e-mail de sauvegarde parmi tous les autres.
DEFAULT_KEYWORDS = [
    "backup",
    "back up",
    "sauvegarde",
    "veeam",
    "acronis",
    "hyper backup",
    "active backup",
    "nakivo",
    "datto",
    "replication",
    "snapshot",
]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "oui", "on"}


def _to_int(value, name: str) -> int:
    """Convertit en entier en remontant un message clair (pas un traceback brut)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} doit être un entier (valeur reçue : {value!r})")


@dataclass
class Config:
    """Configuration complète de l'application."""

    # Source des e-mails : "graph" (Microsoft 365) ou "demo" (mails d'exemple).
    mail_source: str = "demo"

    # Fenêtre de temps minimale (heures). Le board affiche toujours la semaine
    # écoulée (taux de réussite 7 j), donc la fenêtre réelle est d'au moins
    # 7 jours ; lookback_hours ne l'élargit que s'il dépasse cette durée.
    lookback_hours: int = 16

    # --- Microsoft Graph (Microsoft 365 / Outlook) ---
    graph_tenant_id: Optional[str] = None
    graph_client_id: Optional[str] = None
    graph_client_secret: Optional[str] = None
    # Boîte à lire (UPN/adresse), p. ex. "backups@mondomaine.fr".
    graph_mailbox: Optional[str] = None
    # Dossier optionnel à cibler (sinon : toute la boîte de réception).
    graph_folder: Optional[str] = None

    # --- Filtrage ---
    keywords: List[str] = field(default_factory=lambda: list(DEFAULT_KEYWORDS))
    # Si renseigné, un mail d'un expéditeur de confiance est gardé même sans mot-clé.
    trusted_senders: List[str] = field(default_factory=list)

    # Renommage des clients : motif (cherché dans sujet/client/logiciel) -> nom affiché.
    client_aliases: Dict[str, str] = field(default_factory=dict)

    # --- Sortie ---
    output_dir: Path = Path("output")
    dashboard_name: str = "dashboard.html"

    # --- Mode serveur (affichage permanent en kiosque) ---
    serve_host: str = "127.0.0.1"
    serve_port: int = 8470
    serve_hour: int = 7  # heure du scraping quotidien (0-23)

    @property
    def dashboard_path(self) -> Path:
        return self.output_dir / self.dashboard_name

    @classmethod
    def load(cls, path: Optional[str] = None) -> "Config":
        """Charge la configuration depuis le YAML (si présent) puis l'environnement."""
        cfg = cls()

        # 1) Fichier YAML (réglages non secrets).
        cfg_path = Path(path) if path else Path("config.yaml")
        if cfg_path.exists() and yaml is not None:
            data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            cfg.mail_source = data.get("mail_source", cfg.mail_source)
            cfg.lookback_hours = _to_int(
                data.get("lookback_hours", cfg.lookback_hours), "lookback_hours"
            )
            cfg.graph_mailbox = data.get("mailbox", cfg.graph_mailbox)
            cfg.graph_folder = data.get("folder", cfg.graph_folder)
            if data.get("keywords"):
                cfg.keywords = list(data["keywords"])
            if data.get("trusted_senders"):
                cfg.trusted_senders = list(data["trusted_senders"])
            if data.get("client_aliases"):
                cfg.client_aliases = dict(data["client_aliases"])
            output = data.get("output", {})
            if output.get("dir"):
                cfg.output_dir = Path(output["dir"])
            if output.get("name"):
                cfg.dashboard_name = output["name"]
            serve = data.get("serve", {})
            if serve.get("host"):
                cfg.serve_host = str(serve["host"])
            if serve.get("port"):
                cfg.serve_port = _to_int(serve["port"], "serve.port")
            if serve.get("hour") is not None:
                cfg.serve_hour = _to_int(serve["hour"], "serve.hour")

        # 2) Variables d'environnement (priorité aux secrets et aux overrides).
        cfg.mail_source = os.getenv("BACKUPWATCH_SOURCE", cfg.mail_source)
        cfg.lookback_hours = _to_int(
            os.getenv("BACKUPWATCH_LOOKBACK_HOURS", cfg.lookback_hours),
            "BACKUPWATCH_LOOKBACK_HOURS",
        )
        cfg.graph_tenant_id = os.getenv("GRAPH_TENANT_ID", cfg.graph_tenant_id)
        cfg.graph_client_id = os.getenv("GRAPH_CLIENT_ID", cfg.graph_client_id)
        cfg.graph_client_secret = os.getenv("GRAPH_CLIENT_SECRET", cfg.graph_client_secret)
        cfg.graph_mailbox = os.getenv("GRAPH_MAILBOX", cfg.graph_mailbox)
        cfg.graph_folder = os.getenv("GRAPH_FOLDER", cfg.graph_folder)
        if os.getenv("BACKUPWATCH_OUTPUT_DIR"):
            cfg.output_dir = Path(os.environ["BACKUPWATCH_OUTPUT_DIR"])
        cfg.serve_host = os.getenv("BACKUPWATCH_HOST", cfg.serve_host)
        cfg.serve_port = _to_int(os.getenv("BACKUPWATCH_PORT", cfg.serve_port), "BACKUPWATCH_PORT")
        cfg.serve_hour = _to_int(os.getenv("BACKUPWATCH_HOUR", cfg.serve_hour), "BACKUPWATCH_HOUR")

        return cfg

    def validate_graph(self) -> None:
        """Vérifie que les paramètres Graph nécessaires sont présents."""
        missing = [
            name
            for name, value in {
                "GRAPH_TENANT_ID": self.graph_tenant_id,
                "GRAPH_CLIENT_ID": self.graph_client_id,
                "GRAPH_CLIENT_SECRET": self.graph_client_secret,
                "GRAPH_MAILBOX": self.graph_mailbox,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError(
                "Configuration Microsoft Graph incomplète, variables manquantes : "
                + ", ".join(missing)
            )
