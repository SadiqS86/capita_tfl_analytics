#!/usr/bin/env python3
"""Smoke tests for ``agents.nba_agent.NBAAgent`` (Phase 6b).

Examples:
  python scripts/test_nba_agent.py --scenario sla_breach
  python scripts/test_nba_agent.py --scenario all_green
  python scripts/test_nba_agent.py --validate-schema
  python scripts/test_nba_agent.py --no-hallucination
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.nba_agent import NBAAgent
from config import UC_CONFIG


SCENARIOS = {
    "sla_breach": {
        "answer": (
            "SLA compliance is 87.2% this month, down from 93.1% last month. We have 4 breaches "
            "and obligation OBL-042 is now Breached. Atos supplier score has dropped to 62/100."
        ),
        "data_context": {
            "sla_compliance_pct": 87.2,
            "sla_breaches_count": 4,
            "obligation_status": "Breached",
            "supplier_overall_score": 62,
            "days_to_next_audit": 12,
        },
    },
    "all_green": {
        "answer": (
            "All SLAs compliant at 96.4%. No obligations breached. Atos is at 91/100."
        ),
        "data_context": {
            "sla_compliance_pct": 96.4,
            "sla_breaches_count": 0,
            "supplier_overall_score": 91,
            "days_to_next_audit": 60,
        },
    },
    "supplier_amber": {
        "answer": (
            "Supplier overall scores have dropped — Atos is now 68/100, Amber for the third consecutive month."
        ),
        "data_context": {
            "sla_compliance_pct": 92.1,
            "sla_breaches_count": 2,
            "supplier_overall_score": 68,
        },
    },
}

REQUIRED_FIELDS = ("action", "urgency", "rationale", "owner_role", "contract_ref")


def run(scenario: str, *, validate_schema: bool, no_hallucination: bool) -> int:
    spec = SCENARIOS[scenario]
    agent = NBAAgent(UC_CONFIG)
    out = agent.generate(spec["answer"], data_context=spec["data_context"])

    print(f"\n=== scenario: {scenario} ===")
    print(f"matched_rule_count: {out['matched_rule_count']}")
    print(f"data_context:       {json.dumps(out['data_context'], default=str)}")
    print(f"actions ({len(out['actions'])}):")
    for i, a in enumerate(out["actions"], 1):
        print(f"  [{i}] {a['urgency']:9} {a['action']}")
        print(f"       owner={a['owner_role']} | clause={a['contract_ref']}")
        print(f"       rationale={a['rationale']}")

    failures: list[str] = []

    if validate_schema:
        for a in out["actions"]:
            for f in REQUIRED_FIELDS:
                if f not in a:
                    failures.append(f"missing field {f!r}")
                    break

    if no_hallucination:
        # Re-derive allowed refs to assert no LLM hallucinations slipped through.
        from agents.action_rules_agent import ActionRulesAgent

        ra = ActionRulesAgent(UC_CONFIG)
        matched = ra.get_matching_rules(spec["data_context"], max_per_metric=2)
        allowed = {(r.get("contract_ref") or "").strip() for r in matched if r.get("contract_ref")}
        for a in out["actions"]:
            ref = (a.get("contract_ref") or "").strip()
            if ref and ref not in allowed:
                # Allow fuzzy substring match (validator lets these through too)
                if not any(ref.lower() in (x or "").lower() or (x or "").lower() in ref.lower() for x in allowed):
                    failures.append(f"hallucinated contract_ref: {ref!r} not in {allowed!r}")

    if scenario == "sla_breach":
        immediate = [a for a in out["actions"] if a["urgency"] == "Immediate"]
        if not immediate:
            failures.append("expected ≥1 Immediate action for sla_breach scenario")

    if scenario == "all_green":
        non_monitor = [a for a in out["actions"] if a["urgency"] != "Monitor"]
        if non_monitor:
            failures.append(
                f"expected only Monitor actions for all_green, got: "
                f"{[(a['urgency'], a['action'][:40]) for a in non_monitor]}"
            )

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nOK")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", choices=list(SCENARIOS.keys()), default="sla_breach")
    ap.add_argument("--validate-schema", action="store_true")
    ap.add_argument("--no-hallucination", action="store_true")
    ap.add_argument("--all", action="store_true", help="Run every scenario")
    args = ap.parse_args()

    if args.all:
        rc = 0
        for name in SCENARIOS:
            rc |= run(name, validate_schema=True, no_hallucination=True)
        return rc

    return run(args.scenario, validate_schema=args.validate_schema, no_hallucination=args.no_hallucination)


if __name__ == "__main__":
    sys.exit(main())
