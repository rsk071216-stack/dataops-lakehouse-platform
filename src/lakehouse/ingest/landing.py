"""Landing zone: copy each source delivery, byte for byte, into the raw lake.

Local and CI runs land into a folder (file://.lake/landing). In Azure the same
code lands into the private ADLS Gen2 container (az://raw) with the managed
identity. Every delivery writes a _manifest.json that lists exactly the files of
that delivery with their SHA-256, so every load is reproducible and auditable.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import fsspec

from lakehouse.config import FAULT_DIR, FIXTURE_DIR, Settings

LIVE_TRIPS_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data/green_tripdata_{month}.parquet"
LIVE_ZONES_URL = "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv"
FAULT_FILE = "green_trips_late_delivery.csv"


@dataclass(frozen=True)
class LandedFile:
    dataset: str
    uri: str
    name: str
    sha256: str
    bytes: int


def filesystem(url: str) -> tuple[fsspec.AbstractFileSystem, str]:
    """Resolve a landing URL (file://, az://) to an fsspec filesystem and root path."""
    options: dict[str, object] = {}
    if url.startswith(("az://", "abfs://", "abfss://")):
        # No key or SAS: adlfs falls back to DefaultAzureCredential (managed identity).
        options = {"account_name": os.environ["AZURE_STORAGE_ACCOUNT_NAME"], "anon": False}
    fs, root = fsspec.core.url_to_fs(url, **options)
    return fs, root.rstrip("/")


def partition_path(root: str, dataset: str, month: str | None) -> str:
    if dataset == "green_trips":
        return f"{root}/tlc/green_trips/source_month={month}"
    return f"{root}/tlc/{dataset}"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _download(url: str, target: Path) -> Path:
    with urllib.request.urlopen(url, timeout=300) as resp, target.open("wb") as fh:  # noqa: S310
        shutil.copyfileobj(resp, fh)
    return target


def source_files(settings: Settings, workdir: Path) -> dict[str, list[Path]]:
    """The files that make up one delivery, per dataset."""
    if settings.source == "live":
        trips = _download(
            LIVE_TRIPS_URL.format(month=settings.month),
            workdir / f"green_tripdata_{settings.month}.parquet",
        )
        zones = _download(LIVE_ZONES_URL, workdir / "taxi_zone_lookup.csv")
        files = {"green_trips": [trips], "taxi_zones": [zones]}
    else:
        trips = FIXTURE_DIR / f"green_tripdata_{settings.month}.csv"
        if not trips.exists():
            raise FileNotFoundError(f"no fixture for month {settings.month}: {trips}")
        files = {"green_trips": [trips], "taxi_zones": [FIXTURE_DIR / "taxi_zone_lookup.csv"]}
    if settings.inject_bad_records:
        # Simulates an upstream "late correction" file with broken records. The CI
        # negative test uses it to prove Write-Audit-Publish protects production.
        files["green_trips"].append(FAULT_DIR / FAULT_FILE)
    return files


def land(settings: Settings) -> list[LandedFile]:
    """Copy one delivery into the landing zone and write its manifest."""
    fs, root = filesystem(settings.landing_url)
    landed: list[LandedFile] = []
    with tempfile.TemporaryDirectory() as tmp:
        for dataset, paths in source_files(settings, Path(tmp)).items():
            target_dir = partition_path(root, dataset, settings.month)
            fs.makedirs(target_dir, exist_ok=True)
            entries = []
            for path in paths:
                uri = f"{target_dir}/{path.name}"
                fs.put_file(str(path), uri)
                item = LandedFile(dataset, uri, path.name, _sha256(path), path.stat().st_size)
                landed.append(item)
                entries.append(asdict(item))
            manifest = {
                "dataset": dataset,
                "source": settings.source,
                "source_month": settings.month,
                "landed_at": datetime.now(UTC).isoformat(),
                "files": entries,
            }
            with fs.open(f"{target_dir}/_manifest.json", "w") as fh:
                fh.write(json.dumps(manifest, indent=2))
    return landed


def read_manifest(landing_url: str, dataset: str, month: str) -> dict:
    fs, root = filesystem(landing_url)
    with fs.open(f"{partition_path(root, dataset, month)}/_manifest.json", "r") as fh:
        return json.loads(fh.read())
