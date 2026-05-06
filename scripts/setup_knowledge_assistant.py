#!/usr/bin/env python3
"""Create UC volume (if needed), upload PDFs, create Knowledge Assistant + files source; update runtime_resources."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import VolumeType
from databricks.sdk.service.knowledgeassistants import FilesSpec, KnowledgeAssistant, KnowledgeSource

from config import UC_CONFIG
from scripts.runtime_resources_util import merge_runtime_resources

PDF_FILES = (
    "contract_overview.pdf",
    "sla_framework.pdf",
    "supplier_obligations.pdf",
    "governance_compliance.pdf",
)


def _ensure_volume(w: WorkspaceClient, catalog: str, schema: str, volume: str) -> bool:
    path = f"/Volumes/{catalog}/{schema}/{volume}"
    try:
        w.volumes.create(
            catalog_name=catalog,
            schema_name=schema,
            name=volume,
            volume_type=VolumeType.MANAGED,
            comment="TfL contract PDFs for Knowledge Assistant (Phase 4)",
        )
        print(f"Created volume {path}")
        return True
    except Exception as e:
        if "already exists" in str(e).lower() or "RESOURCE_ALREADY_EXISTS" in str(e):
            print(f"Volume exists: {path}")
            return True
        print(f"Volume create error: {e}")
        return False


def _upload_pdfs(w: WorkspaceClient, local_dir: Path, uc_prefix: str) -> int:
    n = 0
    for fname in PDF_FILES:
        local = local_dir / fname
        if not local.exists():
            print(f"Skip missing file: {local}")
            continue
        remote = f"{uc_prefix.rstrip('/')}/{fname}"
        with open(local, "rb") as fh:
            w.files.upload(file_path=remote, contents=fh, overwrite=True)
        print(f"Uploaded {fname} -> {remote}")
        n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description="Knowledge Assistant setup for Capita TfL PDFs.")
    ap.add_argument("--profile", default=os.environ.get("DATABRICKS_CONFIG_PROFILE", "azure_demo"))
    ap.add_argument("--catalog", default=os.environ.get("UC_CATALOG", UC_CONFIG.uc_catalog))
    ap.add_argument("--schema", default=os.environ.get("UC_SCHEMA", UC_CONFIG.uc_schema))
    ap.add_argument(
        "--volume",
        default=os.environ.get("UC_KNOWLEDGE_VOLUME", "tfl_contract_kb"),
    )
    ap.add_argument(
        "--kb-dir",
        type=Path,
        default=ROOT / "use_cases" / "capita_tfl" / "knowledge_base",
        help="Directory containing the four PDFs.",
    )
    ap.add_argument("--skip-volume", action="store_true")
    ap.add_argument("--skip-upload", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    uc_prefix = f"/Volumes/{args.catalog}/{args.schema}/{args.volume}"
    files_spec_path = f"{uc_prefix}/"

    if args.dry_run:
        print(f"[dry-run] would use UC path {files_spec_path}")
        print(f"[dry-run] local KB dir {args.kb_dir}")
        return

    w = WorkspaceClient(profile=args.profile)

    if not args.skip_volume:
        if not _ensure_volume(w, args.catalog, args.schema, args.volume):
            sys.exit(1)

    if not args.skip_upload:
        count = _upload_pdfs(w, args.kb_dir, uc_prefix)
        if count == 0:
            print("No PDFs uploaded. Run: python scripts/generate_pdfs.py")
            sys.exit(1)

    display = os.environ.get("KA_DISPLAY_NAME", "Capita TfL Contract Intelligence")
    desc = (
        "Answers questions about the TfL managed services agreement — SLAs, governance, "
        "supplier obligations, penalties, and reporting using PDFs in Unity Catalog."
    )
    instructions = (
        "Ground answers in the uploaded contract PDFs. Prefer explicit citations. "
        "If asked for live metrics (counts, percentages, breaches), say those come from the analytics agent."
    )

    ka_body = KnowledgeAssistant(
        display_name=display,
        description=desc,
        instructions=instructions,
    )
    created = w.knowledge_assistants.create_knowledge_assistant(knowledge_assistant=ka_body)
    parent = created.name
    if not parent:
        print("Knowledge Assistant create did not return resource name.")
        sys.exit(1)

    ks = KnowledgeSource(
        display_name="TfL contract PDFs",
        description="Unity Catalog volume PDFs for TfL / Capita agreement.",
        source_type="files",
        files=FilesSpec(path=files_spec_path),
    )
    w.knowledge_assistants.create_knowledge_source(parent=parent, knowledge_source=ks)

    merge_runtime_resources(
        {
            "knowledge_assistant_resource_name": parent,
            "knowledge_assistant_id": parent.split("/")[-1],
            "uc_knowledge_volume_path": uc_prefix,
            "catalog": args.catalog,
            "schema": args.schema,
        }
    )
    print(f"Knowledge Assistant resource name: {parent}")
    print("Updated runtime_resources.json (merge). Ingestion may take several minutes.")


if __name__ == "__main__":
    main()
