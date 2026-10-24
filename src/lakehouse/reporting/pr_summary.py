"""Markdown summary of a per-PR dbt build, posted as a sticky PR comment."""

from __future__ import annotations

import json
import os

from lakehouse.config import DBT_PROJECT_DIR, Settings
from lakehouse.dbt_runner import summarize
from lakehouse.warehouse import connect, query

MARKER = "<!-- lakehouse-pr-summary -->"


def _built_relations(target_path: str) -> list[tuple[str, str, str]]:
    root = DBT_PROJECT_DIR / target_path
    run_results = json.loads((root / "run_results.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    out = []
    for result in run_results["results"]:
        node = manifest["nodes"].get(result["unique_id"], {})
        if node.get("resource_type") == "model" and result["status"] == "success":
            out.append((node["name"], node["schema"], node.get("config", {}).get("materialized")))
    return sorted(out)


def render(
    settings: Settings, schema: str, target_path: str, contract_status: str, mode: str
) -> str:
    summary = summarize(target_path)
    relations = _built_relations(target_path)
    rows: list[str] = []
    with connect(settings) as conn:
        for name, rel_schema, materialized in relations:
            n = query(conn, f'select count(*) from "{rel_schema}"."{name}"')[0][0]
            rows.append(f"| `{name}` | `{rel_schema}` | {materialized} | {n:,} |")
    icon = "PASSED" if summary.ok else "FAILED"
    run_url = ""
    if os.environ.get("GITHUB_RUN_ID"):
        run_url = (
            f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/"
            f"{os.environ.get('GITHUB_REPOSITORY')}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
        )
    mode_text = (
        "Slim CI: `state:modified+`, deferred to the production manifest of the last green main run"
        if mode == "slim"
        else "Full build: no production manifest found, every model was built"
    )
    lines = [
        MARKER,
        f"## Lakehouse PR environment: {icon}",
        "",
        f"- **Ephemeral schema:** `{schema}_*` in the CI PostgreSQL service container",
        f"- **Mode:** {mode_text}",
        f"- **Ingestion data contract (ODCS, datacontract-cli):** {contract_status}",
        f"- **Enforced model contracts in project:** {summary.contracts_enforced}",
        "",
        "| Check | Passed | Failed |",
        "|---|---:|---:|",
        f"| Models built | {summary.models_built} | {summary.models_failed} |",
        f"| Data tests | {summary.tests_passed} | {summary.tests_failed} |",
        f"| Unit tests | {summary.unit_tests_passed} | {summary.unit_tests_failed} |",
        "",
        "<details><summary>Models built in this PR and row counts</summary>",
        "",
        "| Model | Schema | Materialization | Rows |",
        "|---|---|---|---:|",
        *(rows or ["| (none) | | | |"]),
        "",
        "</details>",
    ]
    if summary.failures:
        lines += ["", "### Failures", "", "```", *summary.failures[:20], "```"]
    if run_url:
        lines += ["", f"[Workflow run]({run_url})"]
    return "\n".join(lines) + "\n"
