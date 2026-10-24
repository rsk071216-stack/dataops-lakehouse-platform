"""dlt source that loads the landed TLC files into the raw_tlc dataset."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import dlt

from lakehouse.ingest.landing import filesystem, read_manifest
from lakehouse.ingest.schema import GREEN_TRIPS, TAXI_ZONES, dlt_columns, map_row

BATCH_SIZE = 2_000
FROZEN = {"tables": "evolve", "columns": "freeze", "data_type": "freeze"}


def iter_records(uri: str, landing_url: str) -> Iterator[dict[str, Any]]:
    """Stream records from one landed CSV or Parquet file."""
    fs, _ = filesystem(landing_url)
    if uri.endswith(".parquet"):
        import pyarrow.parquet as pq

        with fs.open(uri, "rb") as fh:
            for batch in pq.ParquetFile(fh).iter_batches(batch_size=BATCH_SIZE):
                yield from batch.to_pylist()
    else:
        with fs.open(uri, "rb") as fh:
            yield from csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8", newline=""))


def batched_rows(
    landing_url: str, manifest: dict, mapping: dict, extra: dict[str, Any]
) -> Iterator[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    for entry in manifest["files"]:
        for record in iter_records(entry["uri"], landing_url):
            row = map_row(record, mapping)
            row.update(extra, source_file=entry["name"])
            batch.append(row)
            if len(batch) >= BATCH_SIZE:
                yield batch
                batch = []
    if batch:
        yield batch


@dlt.source(name="tlc", max_table_nesting=0)
def tlc_source(landing_url: str, month: str):
    """NYC TLC green trips (one source month per run) and the taxi zone lookup."""

    @dlt.resource(
        name="green_trips",
        # Idempotent monthly reloads: delete the month, insert the new delivery.
        write_disposition={"disposition": "merge", "strategy": "delete-insert"},
        merge_key="source_month",
        columns=dlt_columns(GREEN_TRIPS),
        # Upstream must not add columns or change types without a reviewed change.
        schema_contract=FROZEN,
    )
    def green_trips() -> Iterator[list[dict[str, Any]]]:
        manifest = read_manifest(landing_url, "green_trips", month)
        extra = {"source_month": month, "ingested_at": datetime.now(UTC)}
        yield from batched_rows(landing_url, manifest, GREEN_TRIPS, extra)

    @dlt.resource(
        name="taxi_zones",
        write_disposition="replace",
        primary_key="location_id",
        columns=dlt_columns(TAXI_ZONES),
        schema_contract=FROZEN,
    )
    def taxi_zones() -> Iterator[list[dict[str, Any]]]:
        manifest = read_manifest(landing_url, "taxi_zones", month)
        extra = {"source_month": month, "ingested_at": datetime.now(UTC)}
        yield from batched_rows(landing_url, manifest, TAXI_ZONES, extra)

    return green_trips, taxi_zones
