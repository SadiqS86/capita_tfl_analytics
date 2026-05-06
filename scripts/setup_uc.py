#!/usr/bin/env python3
"""Create UC schema, run Delta DDL, and load synthetic TfL seed data (Databricks SQL warehouse).

Examples:
  python scripts/setup_uc.py --dry-run
  UC_CATALOG=my_catalog python scripts/setup_uc.py --warehouse-id abc123 --profile azure_demo
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

from dbx_sql import insert_batches, run_statement, split_ddl, substitute_identifiers
from sample_data.seed_tfl_data import build_all, validate_data


def dry_run(catalog: str, schema: str) -> None:
    ddl_path = ROOT / "sample_data" / "create_tfl_tables.sql"
    text = ddl_path.read_text(encoding="utf-8")
    parts = [substitute_identifiers(p, catalog, schema) for p in split_ddl(text)]
    print(f"[dry-run] DDL statements: {len(parts)}")
    for i, p in enumerate(parts):
        head = p.strip().splitlines()[0][:120]
        print(f"  [{i + 1}] {head}…")

    validate_data()
    d, s, sp, m = build_all()
    print(f"[dry-run] Row counts: deliverables={len(d)}, sla={len(s)}, supplier={len(sp)}, metrics={len(m)}")
    print("[dry-run] validate_data OK")


def live_deploy(
    catalog: str,
    schema: str,
    warehouse_id: str,
    profile: str,
    truncate_first: bool,
) -> None:
    validate_data()
    dfs = build_all()

    ddl_path = ROOT / "sample_data" / "create_tfl_tables.sql"
    ddl_parts = [
        substitute_identifiers(p, catalog, schema) for p in split_ddl(ddl_path.read_text(encoding="utf-8"))
    ]

    w = WorkspaceClient(profile=profile)

    schema_sql = f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{schema}`"
    print("Creating schema if not exists…")
    run_statement(w, warehouse_id, schema_sql)

    for part in ddl_parts:
        print("Applying DDL…")
        run_statement(w, warehouse_id, part)

    tables = (
        "contract_deliverables",
        "sla_performance",
        "supplier_performance",
        "contract_monthly_metrics",
    )
    if truncate_first:
        for t in reversed(tables):
            fq = f"`{catalog}`.`{schema}`.`{t}`"
            print(f"Truncating {fq}…")
            run_statement(w, warehouse_id, f"TRUNCATE TABLE {fq}")

    d, s, sp, m = dfs

    stmts: list[str] = []
    stmts.extend(
        insert_batches(
            catalog,
            schema,
            "contract_deliverables",
            (
                "deliverable_id",
                "obligation_ref",
                "title",
                "status",
                "due_date",
                "supplier_name",
                "penalty_exposure_gbp",
                "created_ts",
            ),
            d,
        )
    )
    stmts.extend(
        insert_batches(
            catalog,
            schema,
            "sla_performance",
            (
                "sla_record_id",
                "kpi_name",
                "period_date",
                "is_breach",
                "compliance_pct",
                "breach_reason",
                "supplier_name",
            ),
            s,
        )
    )
    stmts.extend(
        insert_batches(
            catalog,
            schema,
            "supplier_performance",
            (
                "supplier_record_id",
                "supplier_name",
                "period_date",
                "overall_score",
                "rating_band",
                "notes",
            ),
            sp,
        )
    )
    stmts.extend(
        insert_batches(
            catalog,
            schema,
            "contract_monthly_metrics",
            (
                "metrics_row_id",
                "period_date",
                "overall_sla_compliance",
                "next_audit_date",
                "open_deliverables_count",
                "breaches_mtd_count",
            ),
            m,
        )
    )

    for i, stmt in enumerate(stmts):
        print(f"Insert batch {i + 1}/{len(stmts)}…")
        run_statement(w, warehouse_id, stmt)

    print("Done.")


def main() -> None:
    p = argparse.ArgumentParser(description="Unity Catalog setup for Capita TfL demo tables.")
    p.add_argument("--dry-run", action="store_true", help="Validate DDL split + seed only (no API calls).")
    p.add_argument("--catalog", default=os.environ.get("UC_CATALOG", "ss_kibbim_azure_stable"))
    p.add_argument("--schema", default=os.environ.get("UC_SCHEMA", "capita_tfl_demo"))
    p.add_argument("--warehouse-id", default=os.environ.get("DATABRICKS_WAREHOUSE_ID", ""))
    p.add_argument("--profile", default=os.environ.get("DATABRICKS_CONFIG_PROFILE", "azure_demo"))
    p.add_argument(
        "--truncate-first",
        action="store_true",
        help="TRUNCATE tables before insert (after DDL). Use for re-seeding.",
    )
    args = p.parse_args()

    if args.dry_run:
        dry_run(args.catalog, args.schema)
        return

    if not args.warehouse_id.strip():
        print("Error: --warehouse-id or DATABRICKS_WAREHOUSE_ID is required for live deploy.", file=sys.stderr)
        sys.exit(1)

    live_deploy(
        catalog=args.catalog,
        schema=args.schema,
        warehouse_id=args.warehouse_id.strip(),
        profile=args.profile,
        truncate_first=args.truncate_first,
    )


if __name__ == "__main__":
    main()
