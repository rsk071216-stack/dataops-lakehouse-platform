"""Dagster definitions load in both modes and wire lineage from landing to gold.

Run in a subprocess so each mode imports the module with its own environment.
Requires transform/target/manifest.json (`dbt parse`), which CI and `make` create.
"""

import json
import os
import subprocess
import sys

import pytest

from lakehouse.config import DBT_PROJECT_DIR

SCRIPT = """
import json
from lakehouse.orchestration.definitions import defs
g = defs.resolve_asset_graph()
print(json.dumps({
    "assets": sorted(k.to_user_string() for k in g.get_all_asset_keys()),
    "parents": {k.to_user_string(): sorted(p.to_user_string() for p in g.get(k).parent_keys)
                for k in g.get_all_asset_keys()},
    "checks": len(list(g.asset_check_keys)),
    "schedules": [s.name for s in defs.schedules],
}))
"""

pytestmark = pytest.mark.skipif(
    not (DBT_PROJECT_DIR / "target" / "manifest.json").exists(),
    reason="run `dbt parse` first",
)


def _load(target: str) -> dict:
    env = dict(os.environ, LAKEHOUSE_TARGET=target, PGPASSWORD="unused-in-this-test")
    out = subprocess.run(
        [sys.executable, "-c", SCRIPT], env=env, capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_duckdb_mode_lineage_is_connected_end_to_end():
    d = _load("duckdb")
    assert d["parents"]["raw_tlc/green_trips"] == ["landing/tlc_delivery"]
    assert d["parents"]["bronze/stg_tlc__green_trips"] == ["raw_tlc/green_trips"]
    assert "gold/mart_daily_borough_kpis" in d["assets"]
    assert "warehouse/publish" not in d["assets"]
    assert d["checks"] >= 40
    assert d["schedules"] == ["daily_lakehouse_0500_utc"]


def test_postgres_mode_adds_the_publish_step_after_gold():
    d = _load("postgres")
    assert d["parents"]["warehouse/publish"] == [
        "gold/dim_zones",
        "gold/fct_trips",
        "gold/mart_daily_borough_kpis",
        "gold/mart_zone_hourly_demand",
    ]
