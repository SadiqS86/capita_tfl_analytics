"""Seed rows for the ``action_rules`` table (Phase 6a).

Used by ``scripts/setup_action_rules.py`` to populate the threshold rules that
drive the Next Best Action generator. Each rule has:

- ``trigger_metric``: short identifier (sla_compliance_pct, obligation_status, …)
- ``trigger_condition``: SQL-flavoured comparison (``< 90``, ``= Breached``, ``>= 3``)
- ``urgency``: Immediate | This Week | Monitor
- ``contract_ref``: clause anchor for grounding
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pandas as pd

USE_CASE_ID = "capita_tfl"


def _row(
    trigger_metric: str,
    trigger_condition: str,
    urgency: str,
    action_text: str,
    owner_role: str,
    contract_ref: str,
) -> dict:
    return {
        "rule_id": uuid.uuid4().hex,
        "use_case_id": USE_CASE_ID,
        "trigger_metric": trigger_metric,
        "trigger_condition": trigger_condition,
        "urgency": urgency,
        "action_text": action_text,
        "owner_role": owner_role,
        "contract_ref": contract_ref,
        "active": True,
        "created_ts": pd.Timestamp(datetime.now(timezone.utc)),
    }


def build_seed_dataframe() -> pd.DataFrame:
    rows = [
        # SLA compliance — Immediate
        _row(
            "sla_compliance_pct",
            "< 90",
            "Immediate",
            "Initiate formal SLA remediation plan with TfL — clause 8.3 requires submission within 5 working days of falling below 90% compliance.",
            "Contract Manager",
            "Clause 8.3 — SLA Remediation",
        ),
        # SLA compliance — This Week
        _row(
            "sla_compliance_pct",
            "< 95",
            "This Week",
            "Convene SLA performance review with service leads — compliance is approaching the 95% contractual threshold; identify root cause and corrective owner.",
            "Adam Searle",
            "Clause 8.2 — Service Levels",
        ),
        # SLA compliance — Monitor
        _row(
            "sla_compliance_pct",
            ">= 95",
            "Monitor",
            "Track SLA compliance weekly; record any individual KPI dipping below 96% for proactive review.",
            "Service Desk Lead",
            "Schedule 2, Section 4 — Reporting",
        ),
        # Obligation breach — Immediate
        _row(
            "obligation_status",
            "= Breached",
            "Immediate",
            "Raise formal breach notice to TfL contract manager within 48 hours and start remediation tracker — clause 12.1.",
            "Contract Manager",
            "Clause 12.1 — Breach Notification",
        ),
        # Obligation at risk — This Week
        _row(
            "obligation_status",
            "= At Risk",
            "This Week",
            "Escalate at-risk obligation to TfL contract manager and schedule a remediation review within 5 working days.",
            "Contract Manager",
            "Clause 12.2 — Risk Escalation",
        ),
        # Supplier score — Immediate (3+ months Amber)
        _row(
            "supplier_overall_score",
            "< 70",
            "Immediate",
            "Trigger supplier Performance Improvement Plan (PIP) — overall score below 70 / Amber threshold sustained; require 30-day remediation plan.",
            "Adam Searle",
            "Schedule 5 — Supplier Management",
        ),
        # Supplier score — This Week
        _row(
            "supplier_overall_score",
            "< 80",
            "This Week",
            "Request supplier root-cause analysis and improvement commitments — overall score below 80 indicates emerging delivery risk.",
            "Vendor Manager",
            "Schedule 5 — Supplier Management",
        ),
        # Supplier score — Monitor
        _row(
            "supplier_overall_score",
            ">= 80",
            "Monitor",
            "Monthly supplier scorecard review; capture early warning signals before crossing the 80-point threshold.",
            "Vendor Manager",
            "Schedule 5 — Supplier Management",
        ),
        # SLA breaches count — Immediate
        _row(
            "sla_breaches_count",
            ">= 5",
            "Immediate",
            "Convene emergency contract review with TfL — five or more SLA breaches in a single month creates penalty-cap exposure.",
            "Contract Manager",
            "Clause 14.2 — Service Credits",
        ),
        # SLA breaches count — This Week
        _row(
            "sla_breaches_count",
            ">= 3",
            "This Week",
            "Hold root-cause workshop with delivery leads — multiple breaches signal a systemic issue; document remediation owners.",
            "Adam Searle",
            "Clause 14.2 — Service Credits",
        ),
        # Audit window — This Week
        _row(
            "days_to_next_audit",
            "<= 14",
            "This Week",
            "Confirm audit-readiness pack with governance team — next contractual audit is within 14 days.",
            "Governance Lead",
            "Schedule 6 — Audit & Reporting",
        ),
        # Audit window — Monitor
        _row(
            "days_to_next_audit",
            "<= 45",
            "Monitor",
            "Review audit evidence checklist monthly to ensure coverage of all reporting obligations under the contract.",
            "Governance Lead",
            "Schedule 6 — Audit & Reporting",
        ),
    ]
    return pd.DataFrame(rows)
