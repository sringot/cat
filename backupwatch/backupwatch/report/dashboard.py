"""Construit le tableau de bord : board de supervision sobre et glançable.

Un seul objectif : qu'on lève les yeux sur l'écran et qu'on sache en une seconde
si tout va bien ou s'il y a un échec à aller voir. État global + 3 compteurs
(succès / avertissements / échecs) + la liste de ce qui demande une vérification.
"""

from __future__ import annotations

import html
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from string import Template
from typing import Dict, List, Optional

from ..config import Config
from ..models import BackupResult, BackupStatus

TEMPLATE_PATH = Path(__file__).with_name("template.html")
# Police Inter sous-ensemblée (latin) et embarquée en base64 : board 100 %
# autonome, sans police distante ni dépendance CDN.
_FONTS_CSS = Path(__file__).with_name("inter.css").read_text(encoding="utf-8")

_WEEKDAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_MONTHS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]
# Libellé court pour la pastille de chaque ligne « à vérifier ».
_PILL_LABEL = {
    BackupStatus.FAILED: "Échec",
    BackupStatus.WARNING: "Avert.",
    BackupStatus.UNKNOWN: "Inconnu",
}
# Avertissements et inconnus partagent le style ambre ; les échecs, le rouge.
_PILL_CLASS = {
    BackupStatus.FAILED: "fail",
    BackupStatus.WARNING: "warn",
    BackupStatus.UNKNOWN: "warn",
}
_MAX_ATTENTION = 12  # au-delà, on agrège en « +N autres » pour rester lisible


def _esc(value: Optional[str]) -> str:
    return html.escape(value) if value else ""


def _date_long(d: date) -> str:
    s = f"{_WEEKDAYS_FR[d.weekday()]} {d.day} {_MONTHS_FR[d.month - 1]} {d.year}"
    return s[:1].upper() + s[1:]  # « Mardi 23 juin 2026 » (mois en minuscule, FR)


def _counts(results: List[BackupResult]) -> Dict[BackupStatus, int]:
    counts = {status: 0 for status in BackupStatus}
    for result in results:
        counts[result.status] += 1
    return counts


def _plural(n: int) -> str:
    return "s" if n > 1 else ""


def _status_banner(n_total, n_failed, n_warning, n_unknown, n_success):
    """État global affiché en grand : (classe, titre, sous-titre)."""
    if n_total == 0:
        return ("none", "Aucun rapport aujourd'hui",
                "En attente des sauvegardes de la nuit.")
    if n_failed:
        return ("fail", f"{n_failed} échec{_plural(n_failed)} à vérifier",
                f"Sur {n_total} sauvegarde{_plural(n_total)} analysée{_plural(n_total)} aujourd'hui.")
    attention = n_warning + n_unknown
    if attention:
        return ("warn", f"{attention} à surveiller",
                f"Sur {n_total} sauvegarde{_plural(n_total)} analysée{_plural(n_total)} aujourd'hui.")
    return ("ok", "Tout est opérationnel",
            f"{n_success} sauvegarde{_plural(n_success)} réussie{_plural(n_success)} cette nuit.")


def _tile(n: int, label: str, mod: str) -> str:
    zero = " is-zero" if n == 0 else ""
    return (f'<div class="tile tile--{mod}{zero}">'
            f'<div class="tile-num">{n}</div>'
            f'<div class="tile-lbl">{label}</div></div>')


def _attention_html(today_results: List[BackupResult], n_total: int) -> str:
    """Liste de ce qui n'est pas un succès, le plus grave et le plus récent en haut."""
    rows = sorted(
        (r for r in today_results if r.status is not BackupStatus.SUCCESS),
        key=lambda r: (r.status.severity, r.received),
        reverse=True,
    )
    if not rows:
        if n_total == 0:
            return ('<div class="att-empty att-empty--wait">'
                    'En attente des rapports de sauvegarde…</div>')
        return ('<div class="att-empty">'
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
                'stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>'
                'Aucune action requise — toutes les sauvegardes sont passées.</div>')

    items = []
    for r in rows[:_MAX_ATTENTION]:
        tool = _esc(r.source_tool or "")
        time = r.received.astimezone().strftime("%H:%M")
        meta = f"{tool} · {time}" if tool else time
        items.append(
            f'<div class="att-row">'
            f'<span class="pill pill--{_PILL_CLASS[r.status]}">{_PILL_LABEL[r.status]}</span>'
            f'<span class="att-client">{_esc(r.client) or "—"}</span>'
            f'<span class="att-meta">{meta}</span></div>'
        )
    if len(rows) > _MAX_ATTENTION:
        items.append(f'<div class="att-more">+{len(rows) - _MAX_ATTENTION} autres</div>')
    return "".join(items)


def build_dashboard(
    results: List[BackupResult],
    config: Config,
    since: datetime,
    now: Optional[datetime] = None,
) -> Path:
    now = now or datetime.now(timezone.utc)
    today = now.astimezone().date()

    today_results = [r for r in results if r.received.astimezone().date() == today]
    counts = _counts(today_results)
    n_success = counts[BackupStatus.SUCCESS]
    n_warning = counts[BackupStatus.WARNING]
    n_failed = counts[BackupStatus.FAILED]
    n_unknown = counts[BackupStatus.UNKNOWN]
    n_total = len(today_results)

    status_class, status_title, status_sub = _status_banner(
        n_total, n_failed, n_warning, n_unknown, n_success
    )

    # Taux de réussite sur 7 jours (info secondaire, en pied de page).
    days = {today - timedelta(days=i) for i in range(7)}
    week = [r for r in results if r.received.astimezone().date() in days]
    week_success = sum(1 for r in week if r.status is BackupStatus.SUCCESS)
    rate_7d = f"{round(week_success / len(week) * 100)}%" if week else "—"

    if config.mail_source == "graph" and config.graph_mailbox:
        source_label = _esc(config.graph_mailbox)
    elif config.mail_source == "demo":
        source_label = "Démo"
    else:
        source_label = _esc(config.mail_source)

    tiles_html = (
        _tile(n_success, "Succès", "ok")
        + _tile(n_warning, "Avertissements", "warn")
        + _tile(n_failed, "Échecs", "fail")
    )

    template = Template(TEMPLATE_PATH.read_text(encoding="utf-8"))
    page = template.safe_substitute(
        fonts=_FONTS_CSS,
        today_date_long=_date_long(today),
        generated_time=now.astimezone().strftime("%H:%M"),
        source_label=source_label,
        status_class=status_class,
        status_title=status_title,
        status_sub=status_sub,
        tiles_html=tiles_html,
        attention_html=_attention_html(today_results, n_total),
        n_total=n_total,
        rate_7d=rate_7d,
    )

    config.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = config.dashboard_path
    output_path.write_text(page, encoding="utf-8")
    return output_path
