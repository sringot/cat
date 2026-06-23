"""Sources d'e-mails (Microsoft Graph, mode démo) et leur fabrique."""

from __future__ import annotations

from ..config import Config
from .base import MailSource
from .demo import DemoMailSource


def build_source(config: Config) -> MailSource:
    """Construit la source d'e-mails correspondant à la configuration."""
    source = (config.mail_source or "demo").lower()
    if source == "demo":
        return DemoMailSource()
    if source == "graph":
        # Import différé : msal/requests ne sont nécessaires que pour Graph.
        from .graph import GraphMailSource

        return GraphMailSource(config)
    raise ValueError(f"Source d'e-mails inconnue : {config.mail_source!r}")


__all__ = ["MailSource", "DemoMailSource", "build_source"]
