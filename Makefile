# Common developer commands. Everything runs locally on DuckDB, no cloud needed.
# Requires uv (https://docs.astral.sh/uv/). `make help` lists the targets.

SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

export DBT_PROFILES_DIR := $(CURDIR)/transform
export LAKEHOUSE_DUCKDB_PATH := $(CURDIR)/.lake/warehouse.duckdb

UV  := uv run --frozen
DBT := cd transform && $(UV) dbt

.PHONY: help setup lint fmt test contracts ingest build docs run dagster report wap tf-test clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup: ## Install the locked toolchain and dbt packages
	uv sync --frozen
	$(DBT) deps

lint: ## ruff + sqlfluff + yamllint
	$(UV) ruff check .
	$(UV) ruff format --check .
	mkdir -p .lake && cd transform && $(UV) sqlfluff lint models tests
	$(UV) yamllint --strict .

fmt: ## Auto-format Python and SQL
	$(UV) ruff format .
	$(UV) ruff check --fix .
	cd transform && $(UV) sqlfluff fix models tests

test: ## pytest (unit, ingestion, contracts, Dagster definitions)
	$(DBT) parse
	$(UV) pytest

contracts: ## ODCS ingestion contracts against the fixture
	$(UV) datacontract test --server fixture contracts/tlc_green_trips.odcs.yaml
	$(UV) datacontract test --server fixture contracts/tlc_taxi_zones.odcs.yaml

ingest: ## Land the fixture and load raw_tlc with dlt
	$(UV) lakehouse ingest

build: ingest ## dbt build (unit tests, contracts, data tests) on DuckDB
	$(UV) lakehouse build

docs: build ## dbt docs with lineage at http://localhost:8080
	$(DBT) docs generate && $(DBT) docs serve --port 8080

run: ## Materialize every Dagster asset and check in-process
	$(DBT) parse
	$(UV) lakehouse run

dagster: ## Dagster UI at http://localhost:3000
	$(DBT) parse
	$(UV) dagster dev -m lakehouse.orchestration.definitions

report: build ## Data quality report into .lake/site/quality
	$(UV) lakehouse report --out .lake/site/quality

wap: ## Write-Audit-Publish against PostgreSQL (needs PG* env vars)
	LAKEHOUSE_TARGET=postgres $(UV) lakehouse ingest
	LAKEHOUSE_TARGET=postgres $(UV) lakehouse wap

tf-test: ## Terraform fmt, validate and mocked unit tests (no Azure account)
	cd infra/terraform && terraform fmt -check -recursive && terraform init -backend=false -input=false >/dev/null && terraform validate && terraform test

clean: ## Remove local state (warehouse, landing zone, dbt target)
	rm -rf .lake transform/target transform/logs transform/dbt_packages
