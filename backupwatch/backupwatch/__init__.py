"""BackupWatch — surveillance des rapports de sauvegarde par e-mail.

Lit une boîte mail (Microsoft 365 / Outlook via Microsoft Graph), repère les
rapports de sauvegarde de la nuit, en extrait l'état (succès / avertissement /
échec) et génère un tableau de bord web local.
"""

__version__ = "0.1.0"
