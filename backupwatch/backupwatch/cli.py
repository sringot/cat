"""Point d'entrée en ligne de commande.

Exemples :
    python -m backupwatch                 # utilise config.yaml / .env
    python -m backupwatch --source demo   # mode démonstration
    python -m backupwatch --open          # ouvre le rapport dans le navigateur
"""

from __future__ import annotations

import argparse
import logging
import sys
import webbrowser
from collections import Counter

from .config import Config
from .models import BackupStatus
from .pipeline import run


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backupwatch",
        description="Surveille les rapports de sauvegarde reçus par e-mail et "
        "génère un tableau de bord web local.",
    )
    parser.add_argument("--config", help="Chemin du fichier config.yaml")
    parser.add_argument(
        "--source",
        choices=["demo", "graph"],
        help="Source des e-mails (écrase la config)",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        help="Nombre d'heures à analyser en arrière (défaut : 16)",
    )
    parser.add_argument("--open", action="store_true", help="Ouvrir le rapport généré")
    parser.add_argument(
        "--list",
        action="store_true",
        help="Lister chaque rapport détecté (état | logiciel | sujet) — utile au debug",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Logs détaillés")

    # Mode serveur (affichage permanent en kiosque).
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Servir le tableau de bord en continu sur une URL fixe et relancer "
        "le scraping chaque matin (pour un écran de kiosque)",
    )
    parser.add_argument("--host", help="Adresse d'écoute en mode serveur (défaut : 127.0.0.1)")
    parser.add_argument("--port", type=int, help="Port d'écoute en mode serveur (défaut : 8470)")
    parser.add_argument(
        "--hour",
        type=int,
        help="Heure du scraping quotidien en mode serveur, 0-23 (défaut : 7)",
    )
    return parser


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    # En mode serveur, on veut voir l'activité (prochain scraping, rafraîchissements).
    logging.basicConfig(
        level=logging.INFO if (args.verbose or args.serve) else logging.WARNING,
        format="%(levelname)s %(message)s",
    )

    config = Config.load(args.config)
    if args.source:
        config.mail_source = args.source
    if args.lookback:
        config.lookback_hours = args.lookback

    # Mode serveur : affichage permanent en kiosque (boucle infinie, ne retourne
    # qu'à l'arrêt). Les options CLI priment sur la config.
    if args.serve:
        from .serve import serve

        host = args.host or config.serve_host
        port = args.port or config.serve_port
        hour = args.hour if args.hour is not None else config.serve_hour
        if not 0 <= hour <= 23:
            print(f"Erreur : --hour doit être entre 0 et 23 (reçu {hour}).", file=sys.stderr)
            return 1
        return serve(config, host=host, port=port, hour=hour)

    try:
        result = run(config)
    except Exception as exc:  # noqa: BLE001 - on remonte un message clair en CLI
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1

    counts = Counter(r.status for r in result.results)
    print(
        f"Analyse terminée : {result.emails_matched} rapport(s) de sauvegarde "
        f"sur {result.emails_scanned} e-mail(s)."
    )
    print(
        f"  Échecs : {counts[BackupStatus.FAILED]} · "
        f"Avertissements : {counts[BackupStatus.WARNING]} · "
        f"Succès : {counts[BackupStatus.SUCCESS]} · "
        f"Inconnus : {counts[BackupStatus.UNKNOWN]}"
    )
    print(f"Tableau de bord : {result.dashboard_path.resolve()}")

    if args.list:
        print("\nDétail par rapport :")
        ordered = sorted(result.results, key=lambda r: (-r.status.severity, r.client))
        for r in ordered:
            tool = r.source_tool or "?"
            print(f"  {r.status.label_fr:<13} | {tool:<12} | {r.subject[:80]}")

    if args.open:
        webbrowser.open(result.dashboard_path.resolve().as_uri())

    # Code de sortie non nul si au moins un échec (utile pour la supervision).
    return 2 if counts[BackupStatus.FAILED] else 0


if __name__ == "__main__":
    raise SystemExit(main())
