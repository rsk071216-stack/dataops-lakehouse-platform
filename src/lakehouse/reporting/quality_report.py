"""Static data quality report (HTML, no JavaScript) published to GitHub Pages.

Built from dbt's run_results.json + manifest.json and a few warehouse queries,
so it reflects exactly what the last main build verified.
"""

from __future__ import annotations

import html
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from lakehouse.config import DBT_PROJECT_DIR, RAW_DATASET, Settings
from lakehouse.dbt_runner import summarize
from lakehouse.observability import evaluate_freshness
from lakehouse.warehouse import connect, query, row_counts

CSS = """
:root{--bg:#f7f8fa;--fg:#1d2330;--muted:#5b6475;--card:#fff;--line:#e3e6ec;--ok:#1a7f37;--bad:#cf222e;--warn:#9a6700;--accent:#0b5cad}
@media (prefers-color-scheme:dark){:root{--bg:#0f1218;--fg:#e6e9ef;--muted:#9aa3b2;--card:#171b23;--line:#2a303b;--ok:#3fb950;--bad:#f85149;--warn:#d29922;--accent:#58a6ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 48px}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:32px 0 12px}
.muted{color:var(--muted)}a{color:var(--accent)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-top:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.card .v{font-size:26px;font-weight:650;font-variant-numeric:tabular-nums}.card .k{color:var(--muted);font-size:13px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--line);font-size:14px;vertical-align:top}
th{color:var(--muted);font-weight:600}td.n{text-align:right;font-variant-numeric:tabular-nums}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid currentColor}
.pass{color:var(--ok)}.fail,.error{color:var(--bad)}.warn,.skipped{color:var(--warn)}
.scroll{overflow-x:auto}
"""


def _e(value: object) -> str:
    return html.escape(str(value))


def _tests_by_model(target_path: str) -> list[tuple[str, str, str, str]]:
    root = DBT_PROJECT_DIR / target_path
    run_results = json.loads((root / "run_results.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    nodes = manifest.get("nodes", {}) | manifest.get("unit_tests", {})
    rows = []
    for result in run_results["results"]:
        uid = result["unique_id"]
        kind = uid.split(".", 1)[0]
        if kind not in {"test", "unit_test"}:
            continue
        node = nodes.get(uid, {})
        attached = node.get("attached_node") or node.get("model") or ""
        if not attached and node.get("depends_on", {}).get("nodes"):
            attached = ", ".join(n.split(".")[-1] for n in node["depends_on"]["nodes"])
        model = attached.split(".")[-1] if attached else "(project)"
        if kind == "unit_test":
            label = "unit"
        elif node.get("test_metadata"):
            label = "generic"
        else:
            label = "singular"
        rows.append((model, node.get("name", uid), label, result["status"]))
    return sorted(rows)


def build_report(settings: Settings, out_dir: Path, target_path: str = "target") -> Path:
    summary = summarize(target_path)
    prod = settings.prod_schema
    with connect(settings) as conn:
        counts = row_counts(conn, prod)
        rejected = query(
            conn,
            f"select rejection_reason, count(*) from {prod}_silver.int_trips__rejected "
            "group by rejection_reason order by 2 desc",
        )
        bronze_rows = counts.get("bronze.stg_tlc__green_trips", 0)
        last_loaded = query(conn, f"select max(ingested_at) from {RAW_DATASET}.green_trips")[0][0]
        revenue = query(
            conn, f"select coalesce(sum(gross_revenue), 0) from {prod}_gold.mart_daily_borough_kpis"
        )[0][0]
    rejected_total = sum(int(r[1]) for r in rejected)
    rejection_rate = rejected_total / bronze_rows if bronze_rows else 0
    freshness = evaluate_freshness("raw_trips_freshness", last_loaded)
    tests = _tests_by_model(target_path)
    sha = os.environ.get("GITHUB_SHA", "local")[:12]
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    def card(value: object, key: str, cls: str = "") -> str:
        return f'<div class="card"><div class="v {cls}">{_e(value)}</div><div class="k">{_e(key)}</div></div>'

    cards = "".join(
        [
            card(f"{summary.tests_passed + summary.unit_tests_passed}", "tests passed", "pass"),
            card(
                f"{summary.tests_failed + summary.unit_tests_failed}",
                "tests failed",
                "fail" if summary.tests_failed or summary.unit_tests_failed else "pass",
            ),
            card(summary.models_built, "models built"),
            card(summary.contracts_enforced, "gold contracts enforced"),
            card(f"{counts.get('gold.fct_trips', 0):,}", "trips in gold fact"),
            card(
                f"{rejection_rate:.1%}",
                "quarantined in silver (SLO 15%)",
                "pass" if rejection_rate <= 0.15 else "fail",
            ),
            card(f"${float(revenue):,.0f}", "gross revenue in sample"),
            card(
                freshness.message, "raw freshness (SLA 26h)", "pass" if freshness.passed else "fail"
            ),
        ]
    )
    reject_rows = (
        "".join(
            f"<tr><td>{_e(r[0])}</td><td class='n'>{int(r[1]):,}</td>"
            f"<td class='n'>{(int(r[1]) / bronze_rows if bronze_rows else 0):.2%}</td></tr>"
            for r in rejected
        )
        or "<tr><td colspan=3>No rejected rows</td></tr>"
    )
    count_rows = "".join(
        f"<tr><td>{_e(k.split('.')[0])}</td><td><code>{_e(k.split('.')[1])}</code></td>"
        f"<td class='n'>{v:,}</td></tr>"
        for k, v in sorted(
            counts.items(), key=lambda kv: ("bronze silver gold".index(kv[0].split(".")[0]), kv[0])
        )
    )
    test_rows = "".join(
        f"<tr><td><code>{_e(m)}</code></td><td>{_e(n)}</td><td>{_e(kind)}</td>"
        f"<td><span class='pill {_e(s)}'>{_e(s)}</span></td></tr>"
        for m, n, kind, s in tests
    )
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Data Quality Report</title><style>{CSS}</style></head>
<body><main>
<p class="muted"><a href="../">dataops-lakehouse-platform</a> / data quality</p>
<h1>Data quality report</h1>
<p class="muted">Generated {generated} from commit <code>{_e(sha)}</code> on target <code>{_e(settings.target)}</code>,
source month <code>{_e(settings.month)}</code>. Every number below was verified by the CI build that published this page.</p>
<div class="grid">{cards}</div>
<h2>Why rows were quarantined</h2>
<p class="muted">Silver keeps every rejected trip with the first business rule it broke, instead of silently dropping it.</p>
<div class="scroll"><table><thead><tr><th>Rejection reason</th><th>Rows</th><th>Share of delivery</th></tr></thead><tbody>{reject_rows}</tbody></table></div>
<h2>Row counts by layer</h2>
<div class="scroll"><table><thead><tr><th>Layer</th><th>Table</th><th>Rows</th></tr></thead><tbody>{count_rows}</tbody></table></div>
<h2>Test results</h2>
<div class="scroll"><table><thead><tr><th>Model</th><th>Test</th><th>Type</th><th>Status</th></tr></thead><tbody>{test_rows}</tbody></table></div>
<p class="muted" style="margin-top:24px">Lineage and column docs: <a href="../docs/">dbt docs</a>.</p>
</main></body></html>
"""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "index.html"
    path.write_text(page, encoding="utf-8")
    (out_dir / "summary.json").write_text(
        json.dumps(
            {
                "generated_at": generated,
                "git_sha": sha,
                **summary.as_dict(),
                "row_counts": counts,
                "rejected": {r[0]: int(r[1]) for r in rejected},
                "rejection_rate": rejection_rate,
                "freshness": freshness.message,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return path
