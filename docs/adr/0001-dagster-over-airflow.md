# ADR-0001: Dagster (software-defined assets) over Airflow

- Status: accepted
- Date: 2026-10-24

## Context

The platform needs an orchestrator that schedules the pipeline, understands the
dependency graph from raw files to gold marts, runs data checks, and can execute
fully inside CI and inside a short-lived container, without a managed service.

The candidates were Apache Airflow (with Astronomer Cosmos for dbt), Dagster,
and "no orchestrator" (cron plus scripts).

## Decision

Use Dagster with software-defined assets, `dagster-dbt` and `dagster-dlt`.

## Reasons

| Need | Dagster | Airflow + Cosmos |
|---|---|---|
| Unit of work is the *data asset* (table), not a task | Native: every dlt resource and dbt model is an asset with lineage | Tasks; datasets are an add-on |
| dbt tests visible as data quality results | dbt tests become asset checks automatically | Tests are tasks; no per-asset check status |
| Run the whole graph in CI with no services | `materialize()` in-process with an ephemeral instance (done in `ci.yml`) | Needs a metadata DB and scheduler, or `dags test` per DAG |
| Production runtime for a small team | Same code runs in-process in a Container Apps Job; no always-on webserver required | Scheduler + webserver + DB always on (or a paid managed service) |
| Local developer loop | `dagster dev` gives lineage UI on a laptop | Docker Compose with several services |

Cost is the deciding factor for small and mid-size teams: Dagster lets the
production run be a pay-per-second batch job, while Airflow realistically means
an always-on deployment or Astronomer/MWAA/Cloud Composer.

## Consequences

- Asset checks that need history (volume anomaly) store it in the warehouse
  (`lakehouse_ops.volume_history`) because the job's Dagster instance is ephemeral.
- Schedules and sensors in `definitions.py` are used when Dagster runs as a
  long-lived service (`dagster dev`, or Dagster OSS on Container Apps). The
  default Azure deployment uses the Container Apps Job cron instead.
- **Portability:** nothing in `transform/` depends on Dagster. A client standardised
  on Airflow can run the same dbt project with Astronomer Cosmos
  (`DbtTaskGroup(project_config=ProjectConfig("transform"))`) and the same dlt
  pipeline with a PythonOperator; only `src/lakehouse/orchestration/` is replaced.
