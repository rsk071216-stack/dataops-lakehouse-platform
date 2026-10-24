"""Unit tests for the Write-Audit-Publish building blocks (no database needed).

The end-to-end WAP flow, including the negative test, runs against a real
PostgreSQL service container in the `wap-postgres` CI job.
"""

import pytest

from lakehouse.config import Settings
from lakehouse.wap.core import layer_schemas, publish_statements, run_wap, volume_gate


def _render(stmt) -> str:
    """Render psycopg2 sql.Composed without a connection (identifiers only)."""
    out = []
    for part in stmt.seq:
        if hasattr(part, "strings"):  # Identifier
            out.append(".".join(f'"{s}"' for s in part.strings))
        elif hasattr(part, "string"):  # SQL
            out.append(part.string)
        else:
            out.append(_render(part))
    return "".join(out)


def test_first_publish_only_renames_audit_into_place():
    sqls = [_render(s) for s in publish_statements("analytics", "analytics__audit", ("gold",))]
    assert sqls == [
        "set local lock_timeout = '15s'",
        'drop schema if exists "analytics_gold__prev" cascade',
        'alter schema "analytics__audit_gold" rename to "analytics_gold"',
    ]


def test_subsequent_publish_keeps_previous_version_for_rollback():
    sqls = [
        _render(s)
        for s in publish_statements(
            "analytics", "analytics__audit", ("bronze", "gold"), {"bronze": True, "gold": True}
        )
    ]
    assert 'alter schema "analytics_gold" rename to "analytics_gold__prev"' in sqls
    assert 'alter schema "analytics__audit_gold" rename to "analytics_gold"' in sqls
    # Every layer is swapped inside the same statement list = the same transaction.
    assert sum("rename to" in s for s in sqls) == 4


def test_layer_schema_names_follow_dbt_custom_schema_convention():
    assert layer_schemas("pr_42") == ["pr_42_bronze", "pr_42_silver", "pr_42_gold"]


def test_volume_gate_blocks_large_drops_only():
    prod = {"gold.fct_trips": 5000}
    assert volume_gate({"gold.fct_trips": 4900}, prod) is None
    assert "refusing to publish" in volume_gate({"gold.fct_trips": 1000}, prod)
    assert volume_gate({"gold.fct_trips": 10}, {}) is None  # first publish: nothing to compare


def test_wap_refuses_duckdb(monkeypatch):
    monkeypatch.setenv("LAKEHOUSE_TARGET", "duckdb")
    with pytest.raises(RuntimeError, match="postgres"):
        run_wap(Settings())
