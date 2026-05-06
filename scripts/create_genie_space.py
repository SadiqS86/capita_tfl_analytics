#!/usr/bin/env python3
"""Create a Genie space via Databricks API and save ``runtime_resources.json``."""

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
from genie_space_payload import build_serialized_space_string
from scripts.runtime_resources_util import merge_runtime_resources


def main() -> None:
    p = argparse.ArgumentParser(description="Create Genie space for Capita TfL UC tables.")
    p.add_argument("--dry-run", action="store_true", help="Print payload size only; no API calls.")
    p.add_argument("--warehouse-id", default=os.environ.get("DATABRICKS_WAREHOUSE_ID", ""))
    p.add_argument("--profile", default=os.environ.get("DATABRICKS_CONFIG_PROFILE", "azure_demo"))
    p.add_argument("--catalog", default=os.environ.get("UC_CATALOG", UC_CONFIG.uc_catalog))
    p.add_argument("--schema", default=os.environ.get("UC_SCHEMA", UC_CONFIG.uc_schema))
    p.add_argument(
        "--parent-path",
        default=os.environ.get("GENIE_PARENT_PATH", ""),
        help="Workspace folder for the space (optional). Example: /Workspace/Users/you@domain.com",
    )
    p.add_argument(
        "--output",
        default=str(ROOT / "runtime_resources.json"),
        help="Write genie_space_id JSON here.",
    )
    args = p.parse_args()

    serialized = build_serialized_space_string(UC_CONFIG, catalog=args.catalog, schema=args.schema)

    if args.dry_run:
        print(f"[dry-run] serialized_space length: {len(serialized)} chars")
        print(f"[dry-run] warehouse_id={args.warehouse_id or '(unset)'}")
        return

    wid = (args.warehouse_id or "").strip()
    if not wid:
        print("Error: --warehouse-id or DATABRICKS_WAREHOUSE_ID required.", file=sys.stderr)
        sys.exit(1)

    w = WorkspaceClient(profile=args.profile)
    kwargs = {
        "warehouse_id": wid,
        "serialized_space": serialized,
        "title": "TfL Contract Intelligence",
        "description": "Capita TfL SLA, obligations, suppliers — UC-backed Genie space.",
    }
    pp = (args.parent_path or "").strip()
    if pp:
        kwargs["parent_path"] = pp

    space = w.genie.create_space(**kwargs)

    merge_runtime_resources(
        {
            "genie_space_id": space.space_id,
            "warehouse_id": wid,
            "catalog": args.catalog,
            "schema": args.schema,
        },
        path=Path(args.output),
    )
    out_path = Path(args.output)
    print(f"Created Genie space id={space.space_id}")
    print(f"Merged Genie fields into {out_path}")


if __name__ == "__main__":
    main()
