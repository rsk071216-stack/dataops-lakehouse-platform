"""Build the dlt pipeline for the configured warehouse (DuckDB or PostgreSQL)."""

from __future__ import annotations

import os
from urllib.parse import quote

import dlt

from lakehouse.config import RAW_DATASET, REPO_ROOT, Settings
from lakehouse.ingest.source import tlc_source


def postgres_dsn(settings: Settings) -> str:
    pg = settings.postgres
    return (
        f"postgresql://{quote(pg.user, safe='')}:{quote(pg.password(), safe='')}"
        f"@{pg.host}:{pg.port}/{pg.database}?sslmode={pg.sslmode}"
    )


def destination(settings: Settings):
    if settings.target == "duckdb":
        settings.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        return dlt.destinations.duckdb(str(settings.duckdb_path))
    return dlt.destinations.postgres(credentials=postgres_dsn(settings))


def build_pipeline(settings: Settings) -> dlt.Pipeline:
    return dlt.pipeline(
        pipeline_name=f"tlc_{settings.target}",
        destination=destination(settings),
        dataset_name=RAW_DATASET,
        pipelines_dir=os.environ.get(
            "LAKEHOUSE_DLT_DIR", str(REPO_ROOT / ".lake" / "dlt_pipelines")
        ),
    )


def build_source(settings: Settings):
    return tlc_source(landing_url=settings.landing_url, month=settings.month)


def run(settings: Settings):
    """Load the landed delivery into the warehouse raw dataset."""
    pipeline = build_pipeline(settings)
    info = pipeline.run(build_source(settings))
    info.raise_on_failed_jobs()
    return pipeline, info
