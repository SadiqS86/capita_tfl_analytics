#!/usr/bin/env python3
"""Create the ``action_rules`` table and load seed rows (Phase 6a, idempotent).

Examples:
  python scripts/setup_action_rules.py --warehouse-id abc --profile azure_demo
  python scripts/setup_action_rules.py --truncate-first
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from databricks.sdk import WorkspaceClient

from dbx_sql import insert_batches, run_statement
from sample_data.seed_action_rules import build_seed_dataframe


DDL = """
CREATE TABLE IF NOT EXISTS `{catalog}`.`{schema}`.`action_rules` (
  rule_id           STRING NOT NULL,
  use_case_id       STRING NOT NULL,
  trigger_metric    STRING NOT NULL,
  trigger_condition STRING NOT NULL,
  urgency           STRING NOT NULL,
  action_text       STRING NOT NULL,
  owner_role        STRING NOT NULL,
  contract_ref      STRING,
  active            BOOLEAN NOT NULL,
  created_ts        TIMESTAMP NOT NULL
)
USING DELTA
COMMENT 'Configurable threshold rules for Next Best Action generation (Phase 6)'
""".strip()


def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 6a — create + seed action_rules.")
    ap.add_argument("--catalog", default=os.environ.get("UC_CATALOG", "ss_kibbim_azure_stable"))
    ap.add_argument("--schema", default=os.environ.get("UC_SCHEMA", "capita_tfl_demo"))
    ap.add_argument("--warehouse-id", default=os.environ.get("DATABRICKS_WAREHOUSE_ID", ""))
    ap.add_argument("--profile", default=os.environ.get("DATABRICKS_CONFIG_PROFILE", "azure_demo"))
    ap.add_argument("--truncate-first", action="store_true", help="TRUNCATE before insert (re-seed).")
    args = ap.parse_args()

    if not args.warehouse_id.strip():
        print("Error: --warehouse-id or DATABRICKS_WAREHOUSE_ID is required.", file=sys.stderr)
        sys.exit(1)

    w = WorkspaceClient(profile=args.profile)
    fq = f"`{args.catalog}`.`{args.schema}`.`action_rules`"

    print(f"Creating table {fq} (if not exists)…")
    run_statement(w, args.warehouse_id, DDL.format(catalog=args.catalog, schema=args.schema))

    if args.truncate_first:
        print(f"Truncating {fq}…")
        run_statement(w, args.warehouse_id, f"TRUNCATE TABLE {fq}")

    df = build_seed_dataframe()
    print(f"Loading {len(df)} seed rows…")
    stmts = insert_batches(
        args.catalog,
        args.schema,
        "action_rules",
        (
            "rule_id",
            "use_case_id",
            "trigger_metric",
            "trigger_condition",
            "urgency",
            "action_text",
            "owner_role",
            "contract_ref",
            "active",
            "created_ts",
        ),
        df,
        batch_rows=20,
    )
    for i, stmt in enumerate(stmts):
        print(f"Insert batch {i + 1}/{len(stmts)}…")
        run_statement(w, args.warehouse_id, stmt)

    print(f"Done. {len(df)} rules loaded into {fq}.")


if __name__ == "__main__":
    main()
