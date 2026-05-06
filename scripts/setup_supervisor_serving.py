#!/usr/bin/env python3
"""Create a Databricks Supervisor Agent (Genie + Knowledge Assistant tools) via API — same pattern as KA setup."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.supervisoragents import (
    GenieSpace,
    KnowledgeAssistant as SAToolKnowledgeAssistant,
    SupervisorAgent as SASupervisorAgent,
    Tool,
)

from agents.supervisor import build_supervisor_instructions
from config import UC_CONFIG
from scripts.runtime_resources_util import merge_runtime_resources, project_root


def _uuid_from_ka_field(raw: str) -> str:
    """Accept ``knowledge-assistants/{uuid}`` or bare UUID."""
    raw = raw.strip()
    if "/" in raw:
        return raw.split("/")[-1]
    return raw


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Create Supervisor Agent with Genie + Knowledge Assistant tools (POST /api/2.1/supervisor-agents)."
    )
    ap.add_argument("--profile", default=os.environ.get("DATABRICKS_CONFIG_PROFILE", "azure_demo"))
    ap.add_argument(
        "--display-name",
        default=os.environ.get("SUPERVISOR_DISPLAY_NAME", "Capita TfL Supervisor"),
        help="Workspace-unique display name for the supervisor agent.",
    )
    ap.add_argument(
        "--genie-space-id",
        default=os.environ.get("GENIE_SPACE_ID", UC_CONFIG.genie_space_id or ""),
        help="Genie space id (defaults from UC_CONFIG / runtime_resources).",
    )
    ap.add_argument(
        "--knowledge-assistant-id",
        default="",
        help="Knowledge Assistant UUID (defaults from UC_CONFIG / runtime_resources).",
    )
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "artifacts" / "supervisor_manifest.json",
        help="Also write a JSON summary for documentation.",
    )
    args = ap.parse_args()

    genie_id = (args.genie_space_id or "").strip()
    ka_raw = (args.knowledge_assistant_id or "").strip() or UC_CONFIG.knowledge_assistant_id
    ka_uuid = _uuid_from_ka_field(ka_raw) if ka_raw else ""

    instructions = build_supervisor_instructions(UC_CONFIG)
    description = (
        "Routes TfL contract analytics: metrics and operational data via Genie; "
        "contract clauses and governance via Knowledge Assistant."
    )

    manifest = {
        "display_name": args.display_name,
        "description": description,
        "instructions": instructions,
        "genie_space_id": genie_id,
        "knowledge_assistant_id": ka_uuid,
        "tools_to_register": ["genie_space", "knowledge_assistant"],
    }

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote manifest {args.manifest}")

    if args.dry_run:
        print("[dry-run] Skipping supervisor-agents API calls.")
        return

    if not genie_id:
        print("Error: genie_space_id missing. Set GENIE_SPACE_ID or run Phase 3 create_genie_space.", file=sys.stderr)
        sys.exit(1)
    if not ka_uuid:
        print(
            "Error: knowledge_assistant_id missing. Run scripts/setup_knowledge_assistant.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not re.fullmatch(r"[0-9a-fA-F-]{36}", ka_uuid):
        print(f"Error: knowledge_assistant_id should be a UUID; got {ka_uuid!r}", file=sys.stderr)
        sys.exit(1)

    w = WorkspaceClient(profile=args.profile)

    body = SASupervisorAgent(
        display_name=args.display_name,
        description=description,
        instructions=instructions,
    )

    created = w.supervisor_agents.create_supervisor_agent(supervisor_agent=body)
    parent = (created.name or "").strip()
    if not parent:
        print("Error: create_supervisor_agent did not return resource name.", file=sys.stderr)
        sys.exit(1)

    print(f"Created supervisor agent: {parent}")
    if created.endpoint_name:
        print(f"Serving endpoint name: {created.endpoint_name}")

    w.supervisor_agents.create_tool(
        parent=parent,
        tool_id="genie_tfl_metrics",
        tool=Tool(
            tool_type="genie_space",
            description=(
                "Use for SLA compliance, breaches, supplier scores, counts, trends, comparisons, "
                "and lists of deliverables or obligations from operational data."
            ),
            genie_space=GenieSpace(id=genie_id),
        ),
    )
    print("Registered tool: genie_space (genie_tfl_metrics)")

    w.supervisor_agents.create_tool(
        parent=parent,
        tool_id="contract_knowledge_base",
        tool=Tool(
            tool_type="knowledge_assistant",
            description=(
                "Use for contract language: clauses, penalties, governance cadence, audits, "
                "change control, subcontractor rules, and reporting obligations as written in the PDFs."
            ),
            knowledge_assistant=SAToolKnowledgeAssistant(knowledge_assistant_id=ka_uuid),
        ),
    )
    print("Registered tool: knowledge_assistant (contract_knowledge_base)")

    sid = ""
    if parent.startswith("supervisor-agents/"):
        sid = parent.split("/", 1)[1]

    merge_runtime_resources(
        {
            "supervisor_agent_resource_name": parent,
            "supervisor_agent_id": sid,
            "supervisor_endpoint": (created.endpoint_name or "").strip(),
        }
    )
    print(f"Merged supervisor fields into {project_root() / 'runtime_resources.json'}")


if __name__ == "__main__":
    main()
