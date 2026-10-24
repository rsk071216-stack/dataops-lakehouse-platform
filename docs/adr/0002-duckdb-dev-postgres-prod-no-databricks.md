# ADR-0002: DuckDB for development and CI, PostgreSQL for production, no Databricks

- Status: accepted
- Date: 2026-10-24

## Context

The client requirement is explicit: no Databricks and no vendor pipeline
service; everything driven by normal CI/CD. Data volumes for the target teams
are gigabytes to low terabytes, served to BI tools and internal apps.

## Decision

- **DuckDB** is the developer and CI warehouse: zero setup, in-process, fast
  enough to build the whole project in seconds on a GitHub runner.
- **Azure Database for PostgreSQL Flexible Server** is the production warehouse:
  managed, Entra ID authentication, transactional DDL (required for
  Write-Audit-Publish, see ADR-0003), and every BI tool speaks to it.
- **ADLS Gen2** holds the immutable raw landing zone.
- The same dbt project targets both adapters. Models use cross-database macros
  (`dbt.datediff`, `dbt.dateadd`, `dbt_utils.generate_surrogate_key`) and
  portable SQL; CI builds and tests on both.

## Consequences

- Monthly cost is tens of dollars instead of a Databricks workspace plus
  clusters plus a SQL warehouse (see the cost table in the README).
- No vendor lock-in: the warehouse is plain PostgreSQL, the lake is plain
  Parquet/CSV in a storage account, the transformations are plain dbt.
- Postgres is a row store. When a client outgrows it (multi-terabyte scans),
  the dbt project moves to a columnar engine (Azure Synapse/Fabric, Snowflake,
  BigQuery, MotherDuck) by adding a target; ingestion and orchestration stay.
- Contract data types are chosen to be identical on both adapters (`text`,
  `integer`, `bigint`, `decimal(p,s)`, `timestamp`, `date`, `boolean`).
