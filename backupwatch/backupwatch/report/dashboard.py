"""Construit le dashboard : style analytics indigo (hero + KPIs + courbe + radar + jauges + tops)."""

from __future__ import annotations

import html
import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from string import Template
from typing import Dict, List, Optional

from ..config import Config
from ..models import BackupResult, BackupStatus

TEMPLATE_PATH = Path(__file__).with_name("template.html")
_DT_FMT = "%d/%m/%Y · %H:%M"
_WEEKDAYS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]


def _fmt_dt(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone().strftime(_DT_FMT)


def _esc(value: Optional[str]) -> str:
    return html.escape(value) if value else ""


def _counts(results: List[BackupResult]) -> Dict[BackupStatus, int]:
    counts = {status: 0 for status in BackupStatus}
    for result in results:
        counts[result.status] += 1
    return counts


def _rate_int(counts: Dict[BackupStatus, int]) -> Optional[int]:
    total = sum(counts.values())
    return round(counts[BackupStatus.SUCCESS] / total * 100) if total else None


def _pct_delta(cur: int, prev: int) -> str:
    if prev == 0:
        return '<span class="delta flat">—</span>'
    d = round((cur - prev) / prev * 100)
    if d > 0:
        return f'<span class="delta up">&#8593; +{d}%</span>'
    if d < 0:
        return f'<span class="delta down">&#8595; {d}%</span>'
    return '<span class="delta flat">&#8594; 0%</span>'


def _pts_delta(cur: Optional[int], prev: Optional[int]) -> str:
    if cur is None or prev is None:
        return '<span class="delta flat">vs hier : —</span>'
    d = cur - prev
    if d > 0:
        return f'<span class="delta up">&#8593; +{d} pts vs hier</span>'
    if d < 0:
        return f'<span class="delta down">&#8595; {d} pts vs hier</span>'
    return '<span class="delta flat">&#8594; stable vs hier</span>'


def build_dashboard(
    results: List[BackupResult],
    config: Config,
    since: datetime,
    now: Optional[datetime] = None,
) -> Path:
    now = now or datetime.now(timezone.utc)
    today = now.astimezone().date()
    yesterday = today - timedelta(days=1)
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    day_set = set(days)

    buckets: Dict[date, List[BackupResult]] = {d: [] for d in days}
    for result in results:
        d = result.received.astimezone().date()
        if d in day_set:
            buckets[d].append(result)

    week_results = [r for d in days for r in buckets[d]]
    today_results = buckets[today]
    today_counts = _counts(today_results)
    yest_counts = _counts(buckets.get(yesterday, []))
    week_counts = _counts(week_results)

    # Séries hebdomadaires (aires empilées par statut + total pour le hero)
    labels, week_total, week_success, week_warning, week_failed = [], [], [], [], []
    for d in days:
        c = _counts(buckets[d])
        labels.append("Auj." if d == today else _WEEKDAYS[d.weekday()])
        week_total.append(sum(c.values()))
        week_success.append(c[BackupStatus.SUCCESS])
        week_warning.append(c[BackupStatus.WARNING])
        week_failed.append(c[BackupStatus.FAILED])

    # Radar par logiciel
    tool_counter = Counter((r.source_tool or "Autre") for r in week_results)
    tool_items = tool_counter.most_common(6)
    tool_labels = [t for t, _ in tool_items]
    tool_values = [n for _, n in tool_items]

    # Tops
    client_counter = Counter(r.client for r in week_results)
    clients_count = len(client_counter)
    fails = sorted(
        (r for r in week_results if r.status is BackupStatus.FAILED),
        key=lambda r: r.received, reverse=True,
    )
    last_fail = fails[0].client if fails else "Aucun"

    total_7d = len(week_results)
    failed_7d = week_counts[BackupStatus.FAILED]
    warning_7d = week_counts[BackupStatus.WARNING]
    success_7d = week_counts[BackupStatus.SUCCESS]
    rate_7d = _rate_int(week_counts) or 0

    charts = json.dumps({
        "labels": labels,
        "total": week_total,
        "success": week_success,
        "warning": week_warning,
        "failed": week_failed,
        "radarLabels": tool_labels,
        "radar": tool_values,
    }, ensure_ascii=False)

    if config.mail_source == "graph" and config.graph_mailbox:
        source_label = _esc(config.graph_mailbox)
    elif config.mail_source == "demo":
        source_label = "Démo"
    else:
        source_label = _esc(config.mail_source)

    def pct(part: int) -> int:
        return round(part / total_7d * 100) if total_7d else 0

    template = Template(TEMPLATE_PATH.read_text(encoding="utf-8"))
    page = template.safe_substitute(
        generated_at=_fmt_dt(now),
        source_label=source_label,
        today_date=today.strftime("%d/%m/%Y"),
        # Hero
        hero_total=len(today_results),
        hero_delta=_pct_delta(len(today_results), sum(yest_counts.values())),
        # KPIs
        kpi_rate="—" if _rate_int(today_counts) is None else f"{_rate_int(today_counts)}%",
        kpi_rate_delta=_pts_delta(_rate_int(today_counts), _rate_int(yest_counts)),
        kpi_failed=today_counts[BackupStatus.FAILED],
        kpi_warning=today_counts[BackupStatus.WARNING],
        # Jauges (7 j)
        g_rate=f"{rate_7d}%", g_rate_pct=rate_7d,
        g_failed=failed_7d, g_failed_pct=pct(failed_7d),
        g_warning=warning_7d, g_warning_pct=pct(warning_7d),
        success_7d=success_7d, total_7d=total_7d,
        # Tops
        last_fail=_esc(last_fail),
        clients_count=clients_count,
        today_attention=today_counts[BackupStatus.FAILED] + today_counts[BackupStatus.WARNING],
        # Charts data
        charts=charts,
    )

    config.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = config.dashboard_path
    output_path.write_text(page, encoding="utf-8")
    return output_path
