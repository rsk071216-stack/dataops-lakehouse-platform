"""Thin, explicit wrapper around the dbt CLI and its run artifacts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from lakehouse.config import DBT_PROJECT_DIR, Settings


@dataclass
class RunSummary:
    """Counts extracted from dbt's run_results.json and manifest.json."""

    models_built: int = 0
    models_failed: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_warned: int = 0
    unit_tests_passed: int = 0
    unit_tests_failed: int = 0
    skipped: int = 0
    contracts_enforced: int = 0
    failures: list[str] = field(default_factory=list)
    built_models: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.models_failed or self.tests_failed or self.unit_tests_failed)

    def as_dict(self) -> dict:
        return {**self.__dict__, "ok": self.ok}


def dbt_executable() -> str:
    """dbt from PATH, else the one installed next to the running interpreter (venv)."""
    local = Path(sys.executable).with_name("dbt.exe" if os.name == "nt" else "dbt")
    return shutil.which("dbt") or str(local)


def dbt_env(settings: Settings, schema: str) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        DBT_PROFILES_DIR=str(DBT_PROJECT_DIR),
        DBT_TARGET=settings.target,
        DBT_SCHEMA=schema,
        LAKEHOUSE_DUCKDB_PATH=str(settings.duckdb_path),
    )
    if settings.target == "postgres":
        env["PGPASSWORD"] = settings.postgres.password()
    return env


def vars_args() -> list[str]:
    """Optional dbt --vars from LAKEHOUSE_DBT_VARS (YAML/JSON), e.g. production guard rails."""
    value = os.environ.get("LAKEHOUSE_DBT_VARS", "").strip()
    return ["--vars", value] if value else []


def run_dbt(
    settings: Settings, args: list[str], schema: str, target_path: str = "target"
) -> subprocess.CompletedProcess:
    cmd = [dbt_executable(), *args, *vars_args(), "--target-path", target_path]
    print(f"$ dbt {' '.join(args)}  (target={settings.target}, schema={schema})", flush=True)
    return subprocess.run(cmd, cwd=DBT_PROJECT_DIR, env=dbt_env(settings, schema), check=False)


def summarize(target_path: str = "target") -> RunSummary:
    root = DBT_PROJECT_DIR / target_path
    summary = RunSummary()
    run_results = json.loads((root / "run_results.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    nodes = manifest.get("nodes", {}) | manifest.get("unit_tests", {})
    counts: Counter[tuple[str, str]] = Counter()
    for result in run_results["results"]:
        uid, status = result["unique_id"], result["status"]
        kind = uid.split(".", 1)[0]
        counts[(kind, status)] += 1
        if kind == "model" and status == "success":
            summary.built_models.append(nodes.get(uid, {}).get("name", uid))
        if status in {"error", "fail"}:
            summary.failures.append(f"{uid}: {(result.get('message') or status).strip()[:300]}")
    summary.models_built = counts[("model", "success")]
    summary.models_failed = counts[("model", "error")]
    summary.tests_passed = counts[("test", "pass")]
    summary.tests_failed = counts[("test", "fail")] + counts[("test", "error")]
    summary.tests_warned = counts[("test", "warn")]
    summary.unit_tests_passed = counts[("unit_test", "pass")]
    summary.unit_tests_failed = counts[("unit_test", "fail")] + counts[("unit_test", "error")]
    summary.skipped = sum(n for (_, status), n in counts.items() if status == "skipped")
    summary.contracts_enforced = sum(
        1
        for node in manifest.get("nodes", {}).values()
        if node.get("resource_type") == "model"
        and node.get("config", {}).get("contract", {}).get("enforced")
    )
    summary.built_models.sort()
    return summary


if __name__ == "__main__":
    # python -m lakehouse.dbt_runner <target-path>: print a run summary as JSON.
    print(json.dumps(summarize(sys.argv[1] if len(sys.argv) > 1 else "target").as_dict(), indent=2))
