#!/usr/bin/env python3
"""Load leader_profiles seed rows (Adam Searle) into Unity Catalog."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from databricks.sdk import WorkspaceClient

from config import UC_CONFIG
from dbx_sql import insert_batches, run_statement
from sample_data.leader_profile_seed import build_seed_dataframe


def main() -> None:
    p = argparse.ArgumentParser(description="Seed leader_profiles for Capita TfL demo.")
    p.add_argument("--dry-run", action="store_true", help="Print seed preview only.")
    p.add_argument("--catalog", default=os.environ.get("UC_CATALOG", UC_CONFIG.uc_catalog))
    p.add_argument("--schema", default=os.environ.get("UC_SCHEMA", UC_CONFIG.uc_schema))
    p.add_argument("--warehouse-id", default=os.environ.get("DATABRICKS_WAREHOUSE_ID", ""))
    p.add_argument("--profile", default=os.environ.get("DATABRICKS_CONFIG_PROFILE", "azure_demo"))
    p.add_argument("--truncate-first", action="store_true", help="DELETE FROM leader_profiles for this persona first.")
    args = p.parse_args()

    df = build_seed_dataframe(UC_CONFIG)

    if args.dry_run:
        print(f"[dry-run] Would insert {len(df)} rows for persona_id={UC_CONFIG.persona_id}")
        print(df[["question_text", "category", "ask_count", "last_asked_ts"]].to_string(index=False))
        return

    if not args.warehouse_id.strip():
        print("Error: --warehouse-id or DATABRICKS_WAREHOUSE_ID required.", file=sys.stderr)
        sys.exit(1)

    w = WorkspaceClient(profile=args.profile)
    wid = args.warehouse_id.strip()
    fq = f"`{args.catalog}`.`{args.schema}`.`leader_profiles`"

    if args.truncate_first:
        pid = UC_CONFIG.persona_id.replace("'", "''")
        uid = UC_CONFIG.use_case_id.replace("'", "''")
        run_statement(w, wid, f"DELETE FROM {fq} WHERE persona_id = '{pid}' AND use_case_id = '{uid}'")

    cols = (
        "profile_id",
        "persona_id",
        "use_case_id",
        "question_text",
        "category",
        "ask_count",
        "last_asked_ts",
        "source",
        "created_ts",
    )
    for stmt in insert_batches(args.catalog, args.schema, "leader_profiles", cols, df, batch_rows=50):
        run_statement(w, wid, stmt)
    print(f"Inserted {len(df)} rows into {fq}")


if __name__ == "__main__":
    main()
