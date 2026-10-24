"""Warehouse connections and small, dialect-aware helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from lakehouse.config import LAYERS, Settings


@contextmanager
def connect(settings: Settings) -> Iterator:
    """DB-API connection to the configured warehouse (caller controls transactions)."""
    if settings.target == "duckdb":
        import duckdb

        conn = duckdb.connect(str(settings.duckdb_path))
    else:
        import psycopg2

        pg = settings.postgres
        conn = psycopg2.connect(
            host=pg.host,
            port=pg.port,
            dbname=pg.database,
            user=pg.user,
            password=pg.password(),
            sslmode=pg.sslmode,
            connect_timeout=15,
            application_name="lakehouse",
        )
    try:
        yield conn
    finally:
        conn.close()


def query(conn, sql: str, params: tuple = ()) -> list[tuple]:
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def schema_exists(conn, schema: str) -> bool:
    rows = query(
        conn,
        f"select count(*) from information_schema.schemata where schema_name = {_ph(conn)}",
        (schema,),
    )
    return rows[0][0] > 0


def tables_in(conn, schema: str) -> list[str]:
    rows = query(
        conn,
        "select table_name from information_schema.tables "
        f"where table_schema = {_ph(conn)} and table_type = 'BASE TABLE' order by table_name",
        (schema,),
    )
    return [r[0] for r in rows]


def row_counts(conn, base_schema: str, layers: tuple[str, ...] = LAYERS) -> dict[str, int]:
    """Row count of every table in <base>_<layer> schemas, keyed 'layer.table'."""
    counts: dict[str, int] = {}
    for layer in layers:
        schema = f"{base_schema}_{layer}"
        for table in tables_in(conn, schema):
            n = query(conn, f'select count(*) from "{schema}"."{table}"')[0][0]
            counts[f"{layer}.{table}"] = int(n)
    return counts


def _ph(conn) -> str:
    """DB-API paramstyle placeholder: psycopg2 uses %s, DuckDB uses ?."""
    return "%s" if type(conn).__module__.startswith("psycopg2") else "?"
