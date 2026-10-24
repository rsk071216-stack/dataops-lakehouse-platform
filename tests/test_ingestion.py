"""Landing + dlt load into a temporary DuckDB, including the frozen schema contract."""

import csv
import hashlib
import json
from pathlib import Path

import duckdb
import pytest

from lakehouse.config import FIXTURE_DIR, Settings
from lakehouse.ingest import landing, pipeline


def test_fixture_files_match_their_committed_checksums():
    for line in (FIXTURE_DIR / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split()
        assert hashlib.sha256((FIXTURE_DIR / name).read_bytes()).hexdigest() == digest, name


def test_landing_writes_files_and_a_manifest(isolated_env):
    files = landing.land(Settings())
    assert {f.name for f in files} == {"green_tripdata_2024-01.csv", "taxi_zone_lookup.csv"}
    manifest = json.loads(
        (isolated_env / "landing/tlc/green_trips/source_month=2024-01/_manifest.json").read_text()
    )
    assert manifest["source_month"] == "2024-01"
    assert [f["name"] for f in manifest["files"]] == ["green_tripdata_2024-01.csv"]


def test_fault_injection_adds_the_late_delivery_file(isolated_env, monkeypatch):
    monkeypatch.setenv("LAKEHOUSE_INJECT_BAD_RECORDS", "1")
    names = [f.name for f in landing.land(Settings()) if f.dataset == "green_trips"]
    assert names == ["green_tripdata_2024-01.csv", landing.FAULT_FILE]


def test_dlt_loads_typed_raw_tables_idempotently(isolated_env):
    settings = Settings()
    for _ in range(2):  # second run must replace the month, not duplicate it
        landing.land(settings)
        pipeline.run(settings)
    con = duckdb.connect(str(settings.duckdb_path), read_only=True)
    trips = con.sql("select count(*) from raw_tlc.green_trips").fetchone()[0]
    zones = con.sql("select count(*) from raw_tlc.taxi_zones").fetchone()[0]
    types = dict(
        con.sql(
            "select column_name, data_type from information_schema.columns "
            "where table_name = 'green_trips'"
        ).fetchall()
    )
    con.close()
    with (FIXTURE_DIR / "green_tripdata_2024-01.csv").open() as fh:
        expected = sum(1 for _ in csv.DictReader(fh))
    assert trips == expected
    assert zones == 265
    assert types["pickup_datetime"] == "TIMESTAMP"
    assert types["fare_amount"] == "DOUBLE"


def test_new_upstream_column_is_rejected_by_frozen_schema(isolated_env, monkeypatch, tmp_path):
    settings = Settings()
    landing.land(settings)
    pipeline.run(settings)
    # Upstream silently adds a column to next month's delivery.
    drifted = tmp_path / "fixtures"
    drifted.mkdir()
    src = FIXTURE_DIR / "green_tripdata_2024-01.csv"
    rows = list(csv.reader(src.open()))
    rows[0].append("cbd_congestion_fee")
    for row in rows[1:]:
        row.append("0.75")
    with (drifted / "green_tripdata_2024-01.csv").open("w", newline="") as fh:
        csv.writer(fh).writerows(rows)
    (drifted / "taxi_zone_lookup.csv").write_bytes(
        (FIXTURE_DIR / "taxi_zone_lookup.csv").read_bytes()
    )
    monkeypatch.setattr(landing, "FIXTURE_DIR", Path(drifted))
    landing.land(settings)
    with pytest.raises(Exception, match=r"(?i)contract|frozen|freeze"):
        pipeline.run(settings)
