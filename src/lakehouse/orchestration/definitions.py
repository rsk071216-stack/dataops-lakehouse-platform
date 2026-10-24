"""Dagster definitions: software-defined assets from landing to gold.

    landing/tlc_delivery           immutable copy of the source files (+ manifest)
        -> raw_tlc/green_trips      dlt load (frozen schema contract)
        -> raw_tlc/taxi_zones
        -> dbt bronze/silver/gold   dbt build (tests become Dagster asset checks)
        -> warehouse/publish        Write-Audit-Publish swap (PostgreSQL only)

DuckDB mode (local, CI) builds directly into the analytics_* schemas. PostgreSQL
mode builds into the audit schemas and only the publish asset touches production.
"""

import os
import shutil
from collections.abc import Iterator
from dataclasses import asdict
from typing import Any

from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    AssetKey,
    AssetSelection,
    Definitions,
    MaterializeResult,
    ScheduleDefinition,
    asset,
    asset_check,
    define_asset_job,
)
from dagster_dbt import (
    DagsterDbtTranslator,
    DagsterDbtTranslatorSettings,
    DbtCliResource,
    DbtProject,
    dbt_assets,
)
from dagster_dlt import DagsterDltResource, DagsterDltTranslator, dlt_assets
from dagster_dlt.translator import DltResourceTranslatorData

from lakehouse import observability
from lakehouse.config import DBT_PROJECT_DIR, RAW_DATASET, get_settings
from lakehouse.dbt_runner import dbt_env, dbt_executable, vars_args
from lakehouse.ingest import landing
from lakehouse.ingest.pipeline import build_pipeline, build_source
from lakehouse.warehouse import connect, query

settings = get_settings()
WAP_ENABLED = settings.target == "postgres"
BUILD_SCHEMA = settings.audit_schema if WAP_ENABLED else settings.prod_schema
DAGSTER_TARGET_PATH = "target/dagster"

LANDING_KEY = AssetKey(["landing", "tlc_delivery"])
RAW_TRIPS_KEY = AssetKey([RAW_DATASET, "green_trips"])
RAW_ZONES_KEY = AssetKey([RAW_DATASET, "taxi_zones"])
GOLD_MODELS = ("dim_zones", "fct_trips", "mart_daily_borough_kpis", "mart_zone_hourly_demand")


# --------------------------------------------------------------------------- landing
@asset(
    key=LANDING_KEY,
    group_name="ingestion",
    kinds={"python", "azure" if settings.landing_url.startswith("az") else "file"},
    description="Copy the monthly TLC delivery into the raw landing zone with a SHA-256 manifest.",
)
def tlc_delivery(context: AssetExecutionContext) -> MaterializeResult:
    files = landing.land(settings)
    for item in files:
        context.log.info(f"landed {item.name} ({item.bytes} bytes) -> {item.uri}")
    return MaterializeResult(
        metadata={
            "files": [f.name for f in files],
            "bytes": sum(f.bytes for f in files),
            "source": settings.source,
            "source_month": settings.month,
            "sha256": {f.name: f.sha256 for f in files},
        }
    )


# --------------------------------------------------------------------------- dlt -> raw
class RawTranslator(DagsterDltTranslator):
    """Key dlt resources exactly like the dbt sources so lineage connects end to end."""

    def get_asset_spec(self, data: DltResourceTranslatorData):
        spec = super().get_asset_spec(data)
        return spec.replace_attributes(
            key=AssetKey([RAW_DATASET, data.resource.name]),
            deps=[LANDING_KEY],
            group_name="raw",
        )


@dlt_assets(
    dlt_source=build_source(settings),
    dlt_pipeline=build_pipeline(settings),
    name="tlc_raw",
    dagster_dlt_translator=RawTranslator(),
)
def tlc_raw_assets(context: AssetExecutionContext, dlt: DagsterDltResource) -> Iterator[Any]:
    yield from dlt.run(context=context)


# --------------------------------------------------------------------------- dbt
dbt_project = DbtProject(
    project_dir=DBT_PROJECT_DIR,
    profiles_dir=DBT_PROJECT_DIR,
    target=settings.target,
)
dbt_project.prepare_if_dev()


class LakehouseDbtTranslator(DagsterDbtTranslator):
    def get_group_name(self, dbt_resource_props) -> str | None:
        tags = dbt_resource_props.get("tags", [])
        for layer in ("bronze", "silver", "gold"):
            if layer in tags:
                return layer
        return super().get_group_name(dbt_resource_props)


@dbt_assets(
    manifest=dbt_project.manifest_path,
    project=dbt_project,
    dagster_dbt_translator=LakehouseDbtTranslator(
        settings=DagsterDbtTranslatorSettings(enable_asset_checks=True)
    ),
)
def lakehouse_dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource) -> Iterator[Any]:
    # Route the build to the audit schemas (WAP) or straight to analytics (DuckDB).
    os.environ.update(
        {
            k: v
            for k, v in dbt_env(settings, BUILD_SCHEMA).items()
            if k in {"DBT_SCHEMA", "PGPASSWORD", "LAKEHOUSE_DUCKDB_PATH"}
        }
    )
    target_path = DBT_PROJECT_DIR / DAGSTER_TARGET_PATH
    shutil.rmtree(target_path, ignore_errors=True)
    yield from dbt.cli(["build", *vars_args()], context=context, target_path=target_path).stream()


# --------------------------------------------------------------------------- publish (WAP)
@asset(
    key=AssetKey(["warehouse", "publish"]),
    group_name="publish",
    deps=[AssetKey(["gold", m]) for m in GOLD_MODELS],
    kinds={"postgres"},
    description="Atomically swap the audited schemas into production (Write-Audit-Publish).",
)
def warehouse_publish(context: AssetExecutionContext) -> MaterializeResult:
    from lakehouse.dbt_runner import summarize
    from lakehouse.wap.core import publish
    from lakehouse.warehouse import row_counts

    summary = summarize(DAGSTER_TARGET_PATH)
    if not summary.ok:
        raise RuntimeError("refusing to publish: dbt build reported failures")
    with connect(settings) as conn:
        counts = row_counts(conn, settings.audit_schema)
        publish_id = publish(conn, settings, summary, counts)
    context.log.info(f"published {publish_id}")
    return MaterializeResult(metadata={"publish_id": publish_id, "row_counts": counts})


# --------------------------------------------------------------------------- asset checks
def _gold_schema() -> str:
    return f"{BUILD_SCHEMA}_gold"


def _result(verdict: observability.Verdict, severity: AssetCheckSeverity) -> AssetCheckResult:
    observability.emit(verdict, target=settings.target, month=settings.month)
    return AssetCheckResult(
        passed=verdict.passed,
        severity=severity,
        description=verdict.message,
        metadata={k: str(v) for k, v in asdict(verdict).items()},
    )


@asset_check(
    asset=RAW_TRIPS_KEY,
    blocking=True,
    description="Raw trips were loaded within the freshness SLA (26h).",
)
def raw_trips_freshness() -> AssetCheckResult:
    with connect(settings) as conn:
        last = query(conn, f"select max(ingested_at) from {RAW_DATASET}.green_trips")[0][0]
    verdict = observability.evaluate_freshness("raw_trips_freshness", last)
    return _result(verdict, AssetCheckSeverity.ERROR)


@asset_check(
    asset=RAW_TRIPS_KEY,
    description="Raw trip volume stays within 50% of the median of recent loads.",
)
def raw_trips_volume_anomaly() -> AssetCheckResult:
    with connect(settings) as conn:
        ph = "%s" if settings.target == "postgres" else "?"
        current = query(
            conn,
            f"select count(*) from {RAW_DATASET}.green_trips where source_month = {ph}",
            (settings.month,),
        )[0][0]
        history = observability.volume_history(conn, settings, "raw_tlc.green_trips")
        verdict = observability.evaluate_volume("raw_trips_volume_anomaly", history, int(current))
        observability.record_volume(conn, settings, "raw_tlc.green_trips", int(current))
    return _result(verdict, AssetCheckSeverity.WARN)


@asset_check(
    asset=AssetKey(["gold", "fct_trips"]),
    description="Gold fact volume stays within 50% of the median of recent builds.",
)
def fct_trips_volume_anomaly() -> AssetCheckResult:
    with connect(settings) as conn:
        current = query(conn, f"select count(*) from {_gold_schema()}.fct_trips")[0][0]
        history = observability.volume_history(conn, settings, "gold.fct_trips")
        verdict = observability.evaluate_volume("fct_trips_volume_anomaly", history, int(current))
        observability.record_volume(conn, settings, "gold.fct_trips", int(current))
    return _result(verdict, AssetCheckSeverity.WARN)


# --------------------------------------------------------------------------- jobs & schedules
all_assets = [tlc_delivery, tlc_raw_assets, lakehouse_dbt_assets]
if WAP_ENABLED:
    all_assets.append(warehouse_publish)
all_checks = [raw_trips_freshness, raw_trips_volume_anomaly, fct_trips_volume_anomaly]
resources = {
    "dlt": DagsterDltResource(),
    "dbt": DbtCliResource(
        project_dir=dbt_project,
        profiles_dir=str(DBT_PROJECT_DIR),
        target=settings.target,
        dbt_executable=dbt_executable(),
    ),
}

daily_job = define_asset_job("daily_lakehouse", selection=AssetSelection.all())

defs = Definitions(
    assets=all_assets,
    asset_checks=all_checks,
    jobs=[daily_job],
    schedules=[
        ScheduleDefinition(
            name="daily_lakehouse_0500_utc",
            job=daily_job,
            cron_schedule="0 5 * * *",
            execution_timezone="UTC",
        )
    ],
    resources=resources,
)
