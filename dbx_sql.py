"""Shared Databricks SQL utilities (warehouse statement execution)."""

from __future__ import annotations

import math
import time
from typing import Any

import pandas as pd
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import Disposition, Format, StatementState


def split_ddl(sql_text: str) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    for line in sql_text.splitlines():
        if line.strip().startswith("-- DDL_SPLIT"):
            if current:
                chunks.append("\n".join(current).strip())
                current = []
            continue
        current.append(line)
    if current:
        chunks.append("\n".join(current).strip())
    return [c for c in chunks if c.strip().upper().startswith("CREATE")]


def substitute_identifiers(sql: str, catalog: str, schema: str) -> str:
    return sql.replace("__CATALOG__", catalog).replace("__SCHEMA__", schema)


def sql_literal(val: Any) -> str:
    try:
        if val is not None and pd.isna(val):
            return "NULL"
    except TypeError:
        pass
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "NULL"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, pd.Timestamp):
        return f"TIMESTAMP '{val.strftime('%Y-%m-%d %H:%M:%S')}'"
    from datetime import date, datetime

    if isinstance(val, datetime):
        return f"TIMESTAMP '{val.strftime('%Y-%m-%d %H:%M:%S')}'"
    if isinstance(val, date):
        return f"DATE '{val.isoformat()}'"
    if isinstance(val, str):
        return "'" + val.replace("'", "''") + "'"
    return str(val)


def run_statement(w: WorkspaceClient, warehouse_id: str, sql: str) -> None:
    resp = w.statement_execution.execute_statement(
        statement=sql,
        warehouse_id=warehouse_id,
        wait_timeout="50s",
    )
    st = resp.status.state if resp.status else None
    st_ok = st == StatementState.SUCCEEDED
    if st is not None and not st_ok:
        st_ok = str(st).rpartition(".")[-1] == "SUCCEEDED"
    if not st_ok:
        err = resp.status.error.message if resp.status and resp.status.error else str(resp)
        raise RuntimeError(f"SQL failed ({st}): {err}\n---\n{sql[:2000]}")


def fetch_all(w: WorkspaceClient, warehouse_id: str, sql: str) -> list[list[Any]]:
    """Run SELECT and return rows as list of lists (API returns string cells)."""
    resp = w.statement_execution.execute_statement(
        statement=sql,
        warehouse_id=warehouse_id,
        wait_timeout="50s",
        disposition=Disposition.INLINE,
        format=Format.JSON_ARRAY,
    )
    sid = resp.statement_id
    if not sid:
        raise RuntimeError("No statement_id from execute_statement")
    for _ in range(120):
        st = resp.status.state if resp.status else None
        stn = str(st).rpartition(".")[-1] if st else ""
        if stn in ("SUCCEEDED", "FAILED", "CANCELED"):
            break
        time.sleep(1)
        resp = w.statement_execution.get_statement(sid)
    if str(resp.status.state).rpartition(".")[-1] != "SUCCEEDED":
        err = resp.status.error.message if resp.status and resp.status.error else str(resp.status)
        raise RuntimeError(err)
    if not resp.result or not resp.result.data_array:
        return []
    return resp.result.data_array


def insert_batches(
    catalog: str,
    schema: str,
    table: str,
    columns: tuple[str, ...],
    df,
    batch_rows: int = 80,
) -> list[str]:
    stmts: list[str] = []
    fq = f"`{catalog}`.`{schema}`.`{table}`"
    cols_sql = ", ".join(f"`{c}`" for c in columns)
    for start in range(0, len(df), batch_rows):
        part = df.iloc[start : start + batch_rows]
        values_rows = []
        for _, row in part.iterrows():
            vals = ", ".join(sql_literal(row[c]) for c in columns)
            values_rows.append(f"({vals})")
        stmts.append(f"INSERT INTO {fq} ({cols_sql}) VALUES {', '.join(values_rows)}")
    return stmts
