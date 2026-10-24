"""Rebuild the committed CI fixture from the public NYC TLC source.

The fixture is a deterministic 1-in-N sample of one month of NYC TLC green taxi
trips plus the full taxi zone lookup. CI never calls this script; it exists so
anyone can reproduce (and audit) exactly how data/fixtures/tlc was produced.

Usage:
    uv run python scripts/build_fixture.py --month 2024-01 --every 10
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import tempfile
import urllib.request
from pathlib import Path

import pyarrow.parquet as pq

TRIPS_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data/green_tripdata_{month}.parquet"
ZONES_URL = "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv"
OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "tlc"


def _fmt(value: object) -> str:
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _download(url: str, target: Path) -> Path:
    with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 - fixed https URL
        target.write_bytes(resp.read())
    return target


def build(month: str, every: int) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        parquet_path = _download(TRIPS_URL.format(month=month), Path(tmp) / "trips.parquet")
        table = pq.read_table(parquet_path)
    rows = table.to_pylist()
    sample = rows[::every]
    trips_out = OUT_DIR / f"green_tripdata_{month}.csv"
    with trips_out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(table.column_names)
        for row in sample:
            writer.writerow([_fmt(row[c]) for c in table.column_names])
    zones_out = _download(ZONES_URL, OUT_DIR / "taxi_zone_lookup.csv")
    # Normalise to LF bytes so checksums match on every OS and after git checkout.
    zones_out.write_bytes(zones_out.read_bytes().replace(b"\r\n", b"\n"))

    manifest = OUT_DIR / "SHA256SUMS"
    lines = []
    for path in sorted(OUT_DIR.glob("*.csv")):
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    manifest.write_bytes(("\n".join(lines) + "\n").encode())
    print(f"wrote {len(sample)} of {len(rows)} trips to {trips_out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", default="2024-01")
    parser.add_argument("--every", type=int, default=10)
    args = parser.parse_args()
    build(args.month, args.every)
