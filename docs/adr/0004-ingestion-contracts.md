# ADR-0004: dlt ingestion guarded by ODCS contracts and a frozen schema

- Status: accepted
- Date: 2026-10-24

## Context

Most broken dashboards start upstream: a provider renames, drops or retypes a
column, or changes a code list. We want that to fail a pull request or a
scheduled check, loudly, before it reaches the warehouse.

## Decision

Two complementary guards at the ingestion boundary:

1. **Open Data Contract Standard (ODCS v3.2.0)** contracts in `contracts/`,
   tested with `datacontract-cli` 1.2.4. They describe what the producer
   promises: column presence, logical types, required fields, code domains
   (for example payment type 0-6, zone id 1-265) and a minimum row count.
   - CI tests them against the committed fixture on every push and PR.
   - `pytest` proves they *fail* for a dropped column and for out-of-domain codes.
   - `scheduled.yml` tests them weekly against the live upstream files and
     opens an `upstream-drift` issue on failure.
2. **dlt schema contract `columns: freeze, data_type: freeze`** on every
   resource. An unknown upstream column is passed through by the mapper on
   purpose, so dlt rejects the load instead of silently adding a column
   (`tests/test_ingestion.py::test_new_upstream_column_is_rejected_by_frozen_schema`).

Ingestion uses dlt (Python, open source) rather than a vendor service: the
landing step copies files byte for byte into the lake with a SHA-256 manifest,
then dlt loads exactly the files listed in that manifest with an idempotent
`merge` (`delete-insert` on `source_month`).

## Dataset choice

NYC TLC green taxi trips, January 2024 (a deterministic 1-in-10 sample, 5,656
trips, about 560 KB) plus the taxi zone lookup. Public, stable (published
monthly files are immutable), meaningful for an operations story, and it
contains real-world noise (negative fares, zero-distance trips, pickups outside
the file month) that the silver layer has to handle. `scripts/build_fixture.py`
rebuilds the sample reproducibly; `SHA256SUMS` is verified in CI.

## Consequences

- Upstream schema changes need a reviewed PR that updates the mapper, the
  contract and the dbt sources together.
- datacontract-cli runs DuckDB under the hood for file-based servers; the live
  check downloads about 1.4 MB.
