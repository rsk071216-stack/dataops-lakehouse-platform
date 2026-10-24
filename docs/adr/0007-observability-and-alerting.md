# ADR-0007: Data observability and alerting

- Status: accepted
- Date: 2026-10-24

## Context

Tests catch known failure modes. Observability catches the unknown ones: data
that is late, too little, too much, or that silently stops arriving.

## Decision

| Signal | Where | Severity |
|---|---|---|
| Source freshness (`ingested_at`, warn 26h, error 50h) | `dbt source freshness` | warn / error |
| Raw freshness SLA 26h | Dagster asset check `raw_trips_freshness` (blocking) | error |
| Raw volume vs median of last 7 loads (+/- 50%) | Dagster asset check `raw_trips_volume_anomaly` | warn |
| Gold volume vs median of last 7 builds (+/- 50%) | Dagster asset check `fct_trips_volume_anomaly` | warn |
| Row count band per delivery | dbt generic test `row_count_between` | error |
| Rejection rate SLO (<= 15% quarantined) | dbt singular test | error |
| Revenue reconciliation gold vs fact | dbt singular test | error |
| Fact shrinks > 50% vs production | WAP volume gate, refuses publish | error |

Every check result is emitted as one JSON line
(`{"event": "lakehouse.check", "passed": false, ...}`) and every run ends with
`{"event": "lakehouse.run", "success": ...}`.

**Azure:** Container Apps ships stdout to Log Analytics. Two scheduled query
rules (Terraform, `monitoring.tf`) page the action group:

```kusto
ContainerAppConsoleLogs_CL
| where ContainerJobName_s == "caj-lakehouse-pipeline-prod"
| where Log_s has "lakehouse.check"
| extend e = parse_json(Log_s)
| where tobool(e.passed) == false
```

plus a dead man's switch: fewer than one successful `lakehouse.run` event in 24
hours. A resource group budget alerts at 80% forecast and 100% actual.

**GitHub:** `scheduled.yml` runs the full asset graph daily as a canary and the
contracts weekly against live data; failures open or update an issue labelled
`pipeline-canary` or `upstream-drift`.

## Consequences

- Volume history lives in the warehouse (`lakehouse_ops.volume_history`), so
  anomaly detection survives ephemeral job containers.
- New Log Analytics tables (`ContainerAppConsoleLogs` without `_CL`) are used
  by environments created with the newer logging option; adjust the table
  name in `monitoring.tf` if the environment uses it.
