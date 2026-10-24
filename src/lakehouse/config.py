"""Runtime configuration resolved from environment variables.

Everything that differs between a laptop, CI and Azure is an environment
variable, so the same container image runs unchanged in every environment
(12-factor). Defaults target the local DuckDB developer loop.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DBT_PROJECT_DIR = Path(os.environ.get("LAKEHOUSE_DBT_PROJECT_DIR", REPO_ROOT / "transform"))
FIXTURE_DIR = REPO_ROOT / "data" / "fixtures" / "tlc"
FAULT_DIR = REPO_ROOT / "data" / "fixtures" / "faults"
RAW_DATASET = "raw_tlc"
OPS_SCHEMA = "lakehouse_ops"
LAYERS = ("bronze", "silver", "gold")


def _env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PostgresSettings:
    host: str = field(default_factory=lambda: _env("PGHOST", "localhost"))
    port: int = field(default_factory=lambda: int(_env("PGPORT", "5432")))
    database: str = field(default_factory=lambda: _env("PGDATABASE", "lakehouse"))
    user: str = field(default_factory=lambda: _env("PGUSER", "lakehouse"))
    sslmode: str = field(default_factory=lambda: _env("PGSSLMODE", "prefer"))
    # "password" uses PGPASSWORD; "entra" exchanges the managed identity for an
    # Entra ID access token (Azure Database for PostgreSQL Flexible Server).
    auth: str = field(default_factory=lambda: _env("LAKEHOUSE_PG_AUTH", "password"))

    def password(self) -> str:
        if self.auth == "entra":
            from lakehouse.azure_auth import postgres_access_token

            return postgres_access_token()
        return os.environ.get("PGPASSWORD", "")


@dataclass(frozen=True)
class Settings:
    target: str = field(default_factory=lambda: _env("LAKEHOUSE_TARGET", "duckdb"))
    source: str = field(default_factory=lambda: _env("LAKEHOUSE_SOURCE", "fixture"))
    month: str = field(default_factory=lambda: _env("LAKEHOUSE_MONTH", "2024-01"))
    duckdb_path: Path = field(
        default_factory=lambda: Path(
            _env("LAKEHOUSE_DUCKDB_PATH", str(REPO_ROOT / ".lake" / "warehouse.duckdb"))
        )
    )
    landing_url: str = field(
        default_factory=lambda: _env(
            "LAKEHOUSE_LANDING_URL", (REPO_ROOT / ".lake" / "landing").as_uri()
        )
    )
    prod_schema: str = field(default_factory=lambda: _env("LAKEHOUSE_PROD_SCHEMA", "analytics"))
    inject_bad_records: bool = field(default_factory=lambda: _flag("LAKEHOUSE_INJECT_BAD_RECORDS"))
    postgres: PostgresSettings = field(default_factory=PostgresSettings)

    def __post_init__(self) -> None:
        if self.target not in {"duckdb", "postgres"}:
            raise ValueError(f"LAKEHOUSE_TARGET must be duckdb or postgres, got {self.target!r}")
        if self.source not in {"fixture", "live"}:
            raise ValueError(f"LAKEHOUSE_SOURCE must be fixture or live, got {self.source!r}")

    @property
    def audit_schema(self) -> str:
        return f"{self.prod_schema}__audit"


def get_settings() -> Settings:
    return Settings()
