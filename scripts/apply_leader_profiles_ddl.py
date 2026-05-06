#!/usr/bin/env python3
"""Apply only the ``leader_profiles`` CREATE TABLE from ``sample_data/create_tfl_tables.sql``."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from databricks.sdk import WorkspaceClient

from dbx_sql import run_statement, split_ddl, substitute_identifiers


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", default=os.environ.get("UC_CATALOG", "ss_kibbim_azure_stable"))
    p.add_argument("--schema", default=os.environ.get("UC_SCHEMA", "capita_tfl_demo"))
    p.add_argument("--warehouse-id", default=os.environ.get("DATABRICKS_WAREHOUSE_ID", ""))
    p.add_argument("--profile", default=os.environ.get("DATABRICKS_CONFIG_PROFILE", "azure_demo"))
    args = p.parse_args()

    wid = (args.warehouse_id or "").strip()
    if not wid:
        print("Error: --warehouse-id or DATABRICKS_WAREHOUSE_ID required.", file=sys.stderr)
        sys.exit(1)

    text = (ROOT / "sample_data" / "create_tfl_tables.sql").read_text(encoding="utf-8")
    parts = [substitute_identifiers(x, args.catalog, args.schema) for x in split_ddl(text)]
    leader = [p for p in parts if "leader_profiles" in p.lower()]
    if not leader:
        print("Error: leader_profiles DDL block not found.", file=sys.stderr)
        sys.exit(1)

    w = WorkspaceClient(profile=args.profile)
    run_statement(w, wid, f"CREATE SCHEMA IF NOT EXISTS `{args.catalog}`.`{args.schema}`")
    run_statement(w, wid, leader[0])
    print("Applied leader_profiles DDL.")


if __name__ == "__main__":
    main()
