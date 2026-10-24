"""Data observability: freshness and volume anomaly detection plus alert events.

History is stored in the warehouse (lakehouse_ops.volume_history), not in the
Dagster instance, because the production Container Apps Job runs Dagster
in-process with an ephemeral instance. Every check result is also printed as a
single JSON line ("event": "lakehouse.check"); in Azure those lines land in Log
Analytics (ContainerAppConsoleLogs_CL) where a KQL alert rule pages on failures.
"""

from __future__ import annotations

import json
import statistics
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from lakehouse.config import OPS_SCHEMA, Settings

FRESHNESS_SLA_HOURS = 26.0
VOLUME_THRESHOLD = 0.5
MIN_HISTORY = 3
HISTORY_WINDOW = 7


@dataclass(frozen=True)
class Verdict:
    check: str
    passed: bool
    observed: float
    expected: str
    message: str


def evaluate_volume(
    name: str, history: list[int], current: int, threshold: float = VOLUME_THRESHOLD
) -> Verdict:
    """Compare the current row count with the median of recent runs."""
    window = history[-HISTORY_WINDOW:]
    if len(window) < MIN_HISTORY:
        return Verdict(name, True, current, "baseline", f"building baseline ({len(window)} runs)")
    baseline = statistics.median(window)
    if baseline == 0:
        return Verdict(name, current == 0, current, "0", "baseline is zero")
    deviation = (current - baseline) / baseline
    passed = abs(deviation) <= threshold
    return Verdict(
        name,
        passed,
        current,
        f"{baseline:.0f} +/- {threshold:.0%}",
        f"{deviation:+.1%} vs median of last {len(window)} runs",
    )


def evaluate_freshness(
    name: str,
    last_loaded: datetime | None,
    now: datetime | None = None,
    sla_hours: float = FRESHNESS_SLA_HOURS,
) -> Verdict:
    now = now or datetime.now(UTC)
    if last_loaded is None:
        return Verdict(name, False, -1, f"<= {sla_hours}h", "no data loaded yet")
    if last_loaded.tzinfo is None:
        last_loaded = last_loaded.replace(tzinfo=UTC)
    age_h = (now - last_loaded).total_seconds() / 3600
    return Verdict(
        name, age_h <= sla_hours, round(age_h, 2), f"<= {sla_hours}h", f"last load {age_h:.1f}h ago"
    )


def emit(verdict: Verdict, **context: object) -> None:
    """One structured log line per check; the Azure alert rule parses these."""
    event = {
        "event": "lakehouse.check",
        "ts": datetime.now(UTC).isoformat(),
        **asdict(verdict),
        **context,
    }
    print(json.dumps(event, default=str), file=sys.stdout, flush=True)


def emit_run(**fields: object) -> None:
    """Final line of every pipeline run; feeds the "no successful run" alert."""
    event = {"event": "lakehouse.run", "ts": datetime.now(UTC).isoformat(), **fields}
    print(json.dumps(event, default=str), file=sys.stdout, flush=True)


def _ph(settings: Settings) -> str:
    return "%s" if settings.target == "postgres" else "?"


def ensure_history_table(conn, settings: Settings) -> None:
    cur = conn.cursor()
    cur.execute(f"create schema if not exists {OPS_SCHEMA}")
    cur.execute(
        f"create table if not exists {OPS_SCHEMA}.volume_history ("
        " asset_name varchar not null, observed_at timestamp not null, row_count bigint not null)"
    )
    conn.commit()


def volume_history(conn, settings: Settings, asset_name: str) -> list[int]:
    ensure_history_table(conn, settings)
    cur = conn.cursor()
    cur.execute(
        f"select row_count from {OPS_SCHEMA}.volume_history where asset_name = {_ph(settings)}"
        " order by observed_at",
        (asset_name,),
    )
    return [int(r[0]) for r in cur.fetchall()]


def record_volume(conn, settings: Settings, asset_name: str, row_count: int) -> None:
    ph = _ph(settings)
    cur = conn.cursor()
    cur.execute(
        f"insert into {OPS_SCHEMA}.volume_history (asset_name, observed_at, row_count)"
        f" values ({ph}, {ph}, {ph})",
        (asset_name, datetime.now(UTC).replace(tzinfo=None), row_count),
    )
    conn.commit()
