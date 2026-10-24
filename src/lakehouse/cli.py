"""`lakehouse` command line: the single entry point for laptops, CI and Azure.

lakehouse ingest              land the delivery and load it with dlt
lakehouse build               dbt build straight into analytics_* (DuckDB dev loop)
lakehouse wap [--no-publish]  Write-Audit-Publish into PostgreSQL production
lakehouse rollback            swap production back to the previous publish
lakehouse snapshot --out F    record production row counts + last publish id
lakehouse verify-unchanged F  assert production still matches a snapshot
lakehouse run                 materialize every Dagster asset + checks in-process
lakehouse report --out DIR    render the static data quality report
lakehouse pr-summary          markdown summary of a dbt run for a PR comment
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lakehouse.config import OPS_SCHEMA, get_settings

EXIT_AUDIT_FAILED = 2
EXIT_CHECK_FAILED = 3


def cmd_ingest(_: argparse.Namespace) -> int:
    from lakehouse.ingest import landing, pipeline

    settings = get_settings()
    files = landing.land(settings)
    print(f"[ingest] landed {len(files)} file(s) into {settings.landing_url}")
    _, info = pipeline.run(settings)
    print(info)
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    from lakehouse.dbt_runner import run_dbt

    settings = get_settings()
    schema = args.schema or settings.prod_schema
    extra = args.dbt_args[1:] if args.dbt_args[:1] == ["--"] else args.dbt_args
    proc = run_dbt(settings, ["build", *extra], schema=schema)
    return proc.returncode


def cmd_wap(args: argparse.Namespace) -> int:
    from lakehouse.wap import AuditFailedError, run_wap

    settings = get_settings()
    try:
        result = run_wap(
            settings, publish_changes=not args.no_publish, max_volume_drop=args.max_volume_drop
        )
    except AuditFailedError as exc:
        print(f"::error title=Write-Audit-Publish::{str(exc).splitlines()[0]}")
        print(str(exc), file=sys.stderr)
        return EXIT_AUDIT_FAILED
    print(
        json.dumps(
            {
                "publish_id": result.publish_id,
                **result.summary.as_dict(),
                "row_counts": result.row_counts,
            },
            indent=2,
        )
    )
    return 0


def cmd_rollback(_: argparse.Namespace) -> int:
    from lakehouse.wap import rollback

    print(f"[wap] rolled back, id {rollback(get_settings())}")
    return 0


def _snapshot() -> dict:
    from lakehouse.warehouse import connect, query, row_counts, schema_exists

    settings = get_settings()
    with connect(settings) as conn:
        counts = row_counts(conn, settings.prod_schema)
        last = None
        if schema_exists(conn, OPS_SCHEMA):
            rows = query(
                conn,
                f"select publish_id from {OPS_SCHEMA}.publish_log "
                "order by published_at desc limit 1",
            )
            last = rows[0][0] if rows else None
    return {"prod_schema": settings.prod_schema, "last_publish_id": last, "row_counts": counts}


def cmd_snapshot(args: argparse.Namespace) -> int:
    snap = _snapshot()
    Path(args.out).write_text(json.dumps(snap, indent=2), encoding="utf-8")
    print(json.dumps(snap, indent=2))
    return 0


def cmd_verify_unchanged(args: argparse.Namespace) -> int:
    expected = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    actual = _snapshot()
    if not expected["row_counts"]:
        print("snapshot has no production tables; nothing to compare", file=sys.stderr)
        return 1
    if actual != expected:
        print(
            "production CHANGED:\n"
            + json.dumps({"expected": expected, "actual": actual}, indent=2),
            file=sys.stderr,
        )
        return 1
    print(
        f"production unchanged: publish {actual['last_publish_id']}, "
        f"{len(actual['row_counts'])} tables with identical row counts"
    )
    return 0


def cmd_run(_: argparse.Namespace) -> int:
    from dagster import AssetCheckSeverity, DagsterInstance, materialize

    from lakehouse.observability import emit_run
    from lakehouse.orchestration import definitions as d

    with DagsterInstance.ephemeral() as instance:
        result = materialize(
            [*d.all_assets, *d.all_checks],
            instance=instance,
            resources=d.resources,
            raise_on_error=False,
        )
    evaluations = result.get_asset_check_evaluations()
    blocking_failures = []
    for ev in evaluations:
        status = (
            "PASS" if ev.passed else ("FAIL" if ev.severity == AssetCheckSeverity.ERROR else "WARN")
        )
        print(f"[check] {status:4} {ev.asset_key.to_user_string()} :: {ev.check_name}")
        if not ev.passed and ev.severity == AssetCheckSeverity.ERROR:
            blocking_failures.append(ev.check_name)
    materialized = sorted(
        {e.asset_key.to_user_string() for e in result.get_asset_materialization_events()}
    )
    print(
        f"[dagster] success={result.success} assets={len(materialized)} "
        f"checks={len(evaluations)} failed_checks={len(blocking_failures)}"
    )
    emit_run(
        success=result.success and not blocking_failures,
        assets=len(materialized),
        checks=len(evaluations),
        failed_checks=blocking_failures,
    )
    if not result.success:
        return 1
    return EXIT_CHECK_FAILED if blocking_failures else 0


def cmd_report(args: argparse.Namespace) -> int:
    from lakehouse.reporting.quality_report import build_report

    path = build_report(get_settings(), Path(args.out), target_path=args.target_path)
    print(f"[report] wrote {path}")
    return 0


def cmd_pr_summary(args: argparse.Namespace) -> int:
    from lakehouse.reporting.pr_summary import render

    text = render(
        get_settings(),
        schema=args.schema,
        target_path=args.target_path,
        contract_status=args.contract_status,
        mode=args.mode,
    )
    Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lakehouse", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ingest").set_defaults(func=cmd_ingest)

    p = sub.add_parser("build")
    p.add_argument("--schema", default=None)
    p.add_argument("dbt_args", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("wap")
    p.add_argument("--no-publish", action="store_true")
    p.add_argument("--max-volume-drop", type=float, default=0.5)
    p.set_defaults(func=cmd_wap)

    sub.add_parser("rollback").set_defaults(func=cmd_rollback)

    p = sub.add_parser("snapshot")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("verify-unchanged")
    p.add_argument("snapshot")
    p.set_defaults(func=cmd_verify_unchanged)

    sub.add_parser("run").set_defaults(func=cmd_run)

    p = sub.add_parser("report")
    p.add_argument("--out", required=True)
    p.add_argument("--target-path", default="target")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("pr-summary")
    p.add_argument("--schema", required=True)
    p.add_argument("--target-path", default="target")
    p.add_argument("--contract-status", default="unknown")
    p.add_argument("--mode", default="slim")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_pr_summary)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
