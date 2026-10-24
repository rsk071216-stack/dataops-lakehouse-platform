# ADR-0003: Write-Audit-Publish with an atomic schema swap

- Status: accepted
- Date: 2026-10-24

## Context

`dbt build` writes tables in place. If a test fails halfway, dashboards already
read some new tables and some old ones, or a table that is known to be wrong.
We want production to change only when *everything* passed, and all at once.

## Decision

1. **Write**: build every layer into audit schemas (`analytics__audit_bronze`,
   `_silver`, `_gold`), dropped and recreated on every run.
2. **Audit**: the same `dbt build` runs unit tests, enforced model contracts and
   data tests. Extra gates run afterwards; today a volume gate refuses to
   publish if `fct_trips` would shrink by more than 50% versus production.
3. **Publish**: in **one PostgreSQL transaction**, for every layer:
   drop `<prod>_<layer>__prev`, rename `<prod>_<layer>` to `__prev`, rename the
   audit schema to `<prod>_<layer>`, and insert a row into
   `lakehouse_ops.publish_log`. PostgreSQL DDL is transactional, so readers see
   the old version or the new version of every layer, never a mix.
4. **Rollback** is the reverse rename (`lakehouse rollback`), also one
   transaction, using the kept `__prev` schemas.

## Why tables everywhere (no views over raw)

Views in a published schema would read through to `raw_tlc`, which is mutable,
so a bad delivery would leak into "production" before any audit. Bronze is
therefore materialised as tables. Views *inside* the swapped set are safe
because PostgreSQL binds views to object IDs, not names, so renames keep them
pointing at the right tables.

## Verification (in CI, every push)

`ci.yml` job `wap-postgres` runs against a PostgreSQL 16 service container:
good delivery publishes; a broken late delivery (unknown zone 999, payment type
9, vendor 7) fails three bronze tests, exit code 2, publish refused; then
`lakehouse verify-unchanged` proves production has the same publish id and the
same row count in every table; then recovery and rollback are exercised.

## Consequences

- Needs roughly twice the storage of the published layers during a run.
- Objects created outside dbt on top of production schemas (for example a BI
  view in another schema) would be dropped with `__prev` two publishes later
  (`drop schema ... cascade`). Consumers query the gold schema directly.
- DuckDB has no schema rename, so local DuckDB builds go straight to
  `analytics_*`. WAP is a PostgreSQL (production) concern only.
- Grants: schema-level grants move with the schema on rename. Grant reader
  roles on the audit schemas in a dbt `on-run-end` hook if consumers need them.
