"""Column mapping and typing for the NYC TLC ingestion boundary.

The mapping is explicit on purpose: upstream names are renamed to stable
snake_case names here, and anything *not* listed is passed through untouched so
that dlt's frozen schema contract rejects it instead of silently absorbing it.
The ODCS contract in contracts/ describes the same boundary for the producer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

INT, FLOAT, TS, STR = "bigint", "double", "timestamp", "text"

# upstream column -> (warehouse column, dlt data type)
GREEN_TRIPS: dict[str, tuple[str, str]] = {
    "VendorID": ("vendor_id", INT),
    "lpep_pickup_datetime": ("pickup_datetime", TS),
    "lpep_dropoff_datetime": ("dropoff_datetime", TS),
    "store_and_fwd_flag": ("store_and_fwd_flag", STR),
    "RatecodeID": ("ratecode_id", INT),
    "PULocationID": ("pickup_location_id", INT),
    "DOLocationID": ("dropoff_location_id", INT),
    "passenger_count": ("passenger_count", INT),
    "trip_distance": ("trip_distance", FLOAT),
    "fare_amount": ("fare_amount", FLOAT),
    "extra": ("extra", FLOAT),
    "mta_tax": ("mta_tax", FLOAT),
    "tip_amount": ("tip_amount", FLOAT),
    "tolls_amount": ("tolls_amount", FLOAT),
    "ehail_fee": ("ehail_fee", FLOAT),
    "improvement_surcharge": ("improvement_surcharge", FLOAT),
    "total_amount": ("total_amount", FLOAT),
    "payment_type": ("payment_type", INT),
    "trip_type": ("trip_type", INT),
    "congestion_surcharge": ("congestion_surcharge", FLOAT),
}

TAXI_ZONES: dict[str, tuple[str, str]] = {
    "LocationID": ("location_id", INT),
    "Borough": ("borough", STR),
    "Zone": ("zone", STR),
    "service_zone": ("service_zone", STR),
}

LINEAGE_COLUMNS: dict[str, dict[str, Any]] = {
    "source_month": {"data_type": "text", "nullable": False},
    "source_file": {"data_type": "text", "nullable": False},
    "ingested_at": {"data_type": "timestamp", "nullable": False},
}


def dlt_columns(mapping: dict[str, tuple[str, str]], lineage: bool = True) -> dict[str, dict]:
    """dlt column hints for a mapping, plus the lineage columns added on load."""
    cols: dict[str, dict] = {}
    for target, dtype in mapping.values():
        hint: dict[str, Any] = {"data_type": dtype, "nullable": True}
        if dtype == TS:
            # TLC timestamps are New York wall-clock time without an offset.
            hint["timezone"] = False
        cols[target] = hint
    if lineage:
        cols.update(LINEAGE_COLUMNS)
    return cols


def _coerce(value: Any, dtype: str) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return None
    if dtype == INT:
        return int(float(value)) if isinstance(value, str | float) else int(value)
    if dtype == FLOAT:
        return float(value)
    if dtype == TS:
        if isinstance(value, datetime):
            return value.replace(tzinfo=None)
        return datetime.fromisoformat(str(value))
    return str(value)


def map_row(row: dict[str, Any], mapping: dict[str, tuple[str, str]]) -> dict[str, Any]:
    """Rename and type one upstream record. Unknown columns pass through as-is."""
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key in mapping:
            target, dtype = mapping[key]
            try:
                out[target] = _coerce(value, dtype)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"column {key!r}: cannot coerce {value!r} to {dtype}") from exc
        else:
            out[key] = value
    return out
