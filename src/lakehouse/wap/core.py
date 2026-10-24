"""Write-Audit-Publish (WAP) for PostgreSQL.

    WRITE    dbt builds every model into isolated audit schemas
             (<prod>__audit_bronze/_silver/_gold). Production is not touched.
    AUDIT    dbt unit tests, data tests and enforced contracts run inside the same
             build; extra gates (volume drop guard) compare audit with production.
    PUBLISH  only if every check passed: one transaction renames
             prod -> prod__prev and audit -> prod for all layers at once.
             PostgreSQL DDL is transactional, so readers see either the old or the
             new version of *every* layer, never a mix, and never a half-built table.

The previous version is kept as <prod>_<layer>__prev, so `rollback` is a second
rename swap that takes milliseconds. See docs/adr/0003-write-audit-publish.md.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass

from psycopg2 import sql

from lakehouse.config import LAYERS, OPS_SCHEMA, Settings
from lakehouse.dbt_runner import RunSummary, run_dbt, summarize
from lakehouse.warehouse import connect, row_counts, schema_exists

AUDIT_TARGET_PATH = "target/wap-audit"
# Publishing is refused when the audited fact table shrinks by more than this
# share compared to production: a classic symptom of a partial upstream delivery.
DEFAULT_MAX_VOLUME_DROP = 0.5
VOLUME_GATE_TABLE = "gold.fct_trips"


class AuditFailedError(RuntimeError):
    """Raised when the audit fails. Production schemas are left untouched."""

    def __init__(self, message: str, summary: RunSummary | None = None):
        super().__init__(message)
        self.summary = summary


@dataclass
class WapResult:
    publish_id: str
    summary: RunSummary
    row_counts: dict[str, int]


def layer_schemas(base: str, layers: tuple[str, ...] = LAYERS) -> list[str]:
    return [f"{base}_{layer}" for layer in layers]


def publish_statements(
    prod: str,
    audit: str,
    layers: tuple[str, ...] = LAYERS,
    prod_exists: dict[str, bool] | None = None,
) -> list[sql.Composed]:
    """The DDL that atomically swaps audit into production (one transaction)."""
    prod_exists = prod_exists or {}
    stmts: list[sql.Composed] = [sql.SQL("set local lock_timeout = '15s'").format()]
    for layer in layers:
        live = f"{prod}_{layer}"
        prev = f"{prod}_{layer}__prev"
        candidate = f"{audit}_{layer}"
        stmts.append(sql.SQL("drop schema if exists {} cascade").format(sql.Identifier(prev)))
        if prod_exists.get(layer, False):
            stmts.append(
                sql.SQL("alter schema {} rename to {}").format(
                    sql.Identifier(live), sql.Identifier(prev)
                )
            )
        stmts.append(
            sql.SQL("alter schema {} rename to {}").format(
                sql.Identifier(candidate), sql.Identifier(live)
            )
        )
    return stmts


def _ensure_ops_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(sql.SQL("create schema if not exists {}").format(sql.Identifier(OPS_SCHEMA)))
        cur.execute(
            sql.SQL(
                "create table if not exists {}.publish_log ("
                " publish_id text primary key, published_at timestamptz not null default now(),"
                " action text not null, prod_schema text not null, git_sha text,"
                " run_summary jsonb, row_counts jsonb)"
            ).format(sql.Identifier(OPS_SCHEMA))
        )
    conn.commit()


def drop_schemas(conn, schemas: list[str]) -> None:
    with conn.cursor() as cur:
        for schema in schemas:
            cur.execute(sql.SQL("drop schema if exists {} cascade").format(sql.Identifier(schema)))
    conn.commit()


def publish(conn, settings: Settings, summary: RunSummary, counts: dict[str, int]) -> str:
    """Atomically promote the audit schemas to production. Returns the publish id."""
    prod, audit = settings.prod_schema, settings.audit_schema
    _ensure_ops_schema(conn)
    missing = [s for s in layer_schemas(audit) if not schema_exists(conn, s)]
    if missing:
        raise AuditFailedError(f"cannot publish, audit schemas missing: {missing}")
    exists = {layer: schema_exists(conn, f"{prod}_{layer}") for layer in LAYERS}
    publish_id = str(uuid.uuid4())
    try:
        with conn.cursor() as cur:
            for stmt in publish_statements(prod, audit, LAYERS, exists):
                cur.execute(stmt)
            cur.execute(
                sql.SQL(
                    "insert into {}.publish_log (publish_id, action, prod_schema, git_sha,"
                    " run_summary, row_counts) values (%s, 'publish', %s, %s, %s, %s)"
                ).format(sql.Identifier(OPS_SCHEMA)),
                (
                    publish_id,
                    prod,
                    os.environ.get("GITHUB_SHA") or os.environ.get("LAKEHOUSE_GIT_SHA"),
                    json.dumps(summary.as_dict()),
                    json.dumps(counts),
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return publish_id


def rollback(settings: Settings) -> str:
    """Swap production with the previously published version (both kept)."""
    prod = settings.prod_schema
    with connect(settings) as conn:
        _ensure_ops_schema(conn)
        for layer in LAYERS:
            if not schema_exists(conn, f"{prod}_{layer}__prev"):
                raise RuntimeError(f"nothing to roll back to: {prod}_{layer}__prev missing")
        rollback_id = str(uuid.uuid4())
        try:
            with conn.cursor() as cur:
                cur.execute("set local lock_timeout = '15s'")
                for layer in LAYERS:
                    live, prev, tmp = (
                        f"{prod}_{layer}",
                        f"{prod}_{layer}__prev",
                        f"{prod}_{layer}__swap",
                    )
                    for a, b in ((live, tmp), (prev, live), (tmp, prev)):
                        cur.execute(
                            sql.SQL("alter schema {} rename to {}").format(
                                sql.Identifier(a), sql.Identifier(b)
                            )
                        )
                cur.execute(
                    sql.SQL(
                        "insert into {}.publish_log (publish_id, action, prod_schema)"
                        " values (%s, 'rollback', %s)"
                    ).format(sql.Identifier(OPS_SCHEMA)),
                    (rollback_id, prod),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return rollback_id


def volume_gate(
    audit_counts: dict[str, int],
    prod_counts: dict[str, int],
    max_drop: float = DEFAULT_MAX_VOLUME_DROP,
) -> str | None:
    """Return a failure message when the audited fact shrank too much vs production."""
    before = prod_counts.get(VOLUME_GATE_TABLE)
    after = audit_counts.get(VOLUME_GATE_TABLE)
    if not before or after is None:
        return None
    if after < before * (1 - max_drop):
        return (
            f"volume gate: {VOLUME_GATE_TABLE} would drop from {before} to {after} rows "
            f"(more than {max_drop:.0%}); refusing to publish"
        )
    return None


def run_wap(
    settings: Settings,
    publish_changes: bool = True,
    max_volume_drop: float = DEFAULT_MAX_VOLUME_DROP,
) -> WapResult:
    if settings.target != "postgres":
        raise RuntimeError("Write-Audit-Publish needs LAKEHOUSE_TARGET=postgres (schema renames)")
    audit = settings.audit_schema
    with connect(settings) as conn:
        # WRITE: always start from empty audit schemas so nothing stale is published.
        drop_schemas(conn, layer_schemas(audit))
    print(f"[wap] WRITE + AUDIT into {audit}_*", flush=True)
    proc = run_dbt(settings, ["build"], schema=audit, target_path=AUDIT_TARGET_PATH)
    summary = summarize(AUDIT_TARGET_PATH)
    if proc.returncode != 0 or not summary.ok:
        raise AuditFailedError(
            "audit failed, production untouched:\n  " + "\n  ".join(summary.failures[:20]),
            summary,
        )
    with connect(settings) as conn:
        audit_counts = row_counts(conn, audit)
        prod_counts = row_counts(conn, settings.prod_schema)
        gate = volume_gate(audit_counts, prod_counts, max_volume_drop)
        if gate:
            raise AuditFailedError(gate, summary)
        if not publish_changes:
            print("[wap] audit passed, publish skipped (--no-publish)", flush=True)
            return WapResult("", summary, audit_counts)
        print(f"[wap] PUBLISH {audit}_* -> {settings.prod_schema}_* (single transaction)")
        publish_id = publish(conn, settings, summary, audit_counts)
    print(f"[wap] published {publish_id}", flush=True)
    return WapResult(publish_id, summary, audit_counts)
