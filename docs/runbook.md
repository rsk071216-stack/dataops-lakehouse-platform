# Runbook

Operational procedures for the production deployment. Every command is the
same `lakehouse` CLI that CI uses.

## A publish was refused (audit failed)

Symptom: the job exits with code 2, log line `::error title=Write-Audit-Publish::audit failed`.
Production is unchanged by design.

1. Read the failing tests in the job log, or query the audit schemas, which are
   kept until the next run: `select * from analytics__audit_bronze.stg_tlc__green_trips where pickup_zone_id not in (select zone_id from analytics__audit_bronze.stg_tlc__taxi_zones);`
2. Upstream problem (bad delivery): contact the producer (see `support` in the
   contract), keep production on the last good version, nothing else to do.
3. Our problem (logic change): fix in a PR; slim CI shows the effect in `pr_<n>_*`.

## Roll back the last publish

```bash
lakehouse rollback          # swaps analytics_* with analytics_*__prev in one transaction
lakehouse snapshot --out now.json
```

`lakehouse_ops.publish_log` records every publish and rollback with the git SHA.

## Re-run the pipeline now

```bash
az containerapp job start -g rg-lakehouse-prod -n caj-lakehouse-pipeline-prod
```

## Upstream drift issue opened by `scheduled.yml`

The live file no longer matches `contracts/`. Update, in one PR: the mapper in
`src/lakehouse/ingest/schema.py`, the ODCS contract, `_tlc__sources.yml` and the
staging model. The frozen dlt schema will reject the load until then.

## Volume anomaly warning

Warn-level checks do not block publishing. Compare `lakehouse_ops.volume_history`
with the TLC release notes (holidays and weather move volumes legitimately).
Tighten or loosen `VOLUME_THRESHOLD` in `src/lakehouse/observability.py` if needed.

## Override guard rails for a full-volume month

The default `min_monthly_trips` and `max_monthly_trips` fit the CI fixture. For
production volumes set the job environment variable
`LAKEHOUSE_DBT_VARS='{min_monthly_trips: 30000, max_monthly_trips: 200000}'`
(Terraform `pipeline_env`); every dbt invocation passes it as `--vars`.

## Tear down an environment

```bash
cd infra/terraform
terraform init -backend-config=...   # same values as deploy.yml
terraform destroy -var-file=environments/dev.tfvars \
  -var subscription_id=... -var image=... -var 'postgres_entra_admin={...}'
```

Key Vault has purge protection: the name stays reserved for the soft-delete
period (30 days). Change `name_suffix` to redeploy sooner.
