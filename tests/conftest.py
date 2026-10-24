"""Shared fixtures. Every test runs offline against temporary DuckDB files."""

from __future__ import annotations

import pytest


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Point landing zone, warehouse and dlt state at a throwaway directory."""
    monkeypatch.setenv("LAKEHOUSE_TARGET", "duckdb")
    monkeypatch.setenv("LAKEHOUSE_SOURCE", "fixture")
    monkeypatch.setenv("LAKEHOUSE_DUCKDB_PATH", str(tmp_path / "warehouse.duckdb"))
    monkeypatch.setenv("LAKEHOUSE_LANDING_URL", (tmp_path / "landing").as_uri())
    monkeypatch.delenv("LAKEHOUSE_INJECT_BAD_RECORDS", raising=False)
    monkeypatch.setenv("LAKEHOUSE_DLT_DIR", str(tmp_path / "dlt"))
    return tmp_path
