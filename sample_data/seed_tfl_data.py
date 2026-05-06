"""Synthetic TfL / Capita demo data — row counts and distributions match PLAN.md Phase 2."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)

# Demo timeline: 24 months ending May 2026 (aligns with exec rehearsal date).
_MONTH_START = date(2024, 6, 1)
_MONTHS_24: list[date] = []
for i in range(24):
    y, m = _MONTH_START.year + (_MONTH_START.month - 1 + i) // 12, (_MONTH_START.month - 1 + i) % 12 + 1
    _MONTHS_24.append(date(y, m, 1))

_CURRENT_MONTH_START = _MONTHS_24[-1]  # May 2026

KPI_NAMES: tuple[str, ...] = (
    "Incident Response Time",
    "Resolution SLA",
    "Platform Availability",
    "Quality Score",
    "Reporting Timeliness",
    "Change Success Rate",
    "Customer Satisfaction",
    "Data Accuracy",
    "Security Patch SLA",
    "Backup Completion",
    "Capacity Alert Response",
    "Major Incident Comms",
    "Problem Ticket Backlog",
    "Release Deployment Window",
    "API Latency P95",
    "Escalation Handling",
    "Knowledge Base Updates",
    "Audit Evidence Submission",
    "Financial Reconciliation",
    "Governance Attendance",
)

SUPPLIERS: tuple[str, ...] = (
    "Atos UK",
    "Accenture Operations",
    "ServiceNow SI Partner",
    "TfL Shared Services",
    "Capita Digital Delivery",
)

# Two suppliers stay Amber / below 70 average for the demo narrative.
_LOW_SUPPLIERS = {"Atos UK", "Accenture Operations"}


def build_contract_deliverables() -> pd.DataFrame:
    """~200 rows: 60% Complete, 20% Open, 10% At Risk, 5% Breached (+ remainder Complete)."""
    n = 200
    status_counts = {"Complete": 120, "Open": 40, "At Risk": 20, "Breached": 10}
    assigned = sum(status_counts.values())
    status_counts["Complete"] += n - assigned  # absorb rounding remainder

    statuses: list[str] = []
    for s, c in status_counts.items():
        statuses.extend([s] * c)
    RNG.shuffle(statuses)

    rows = []
    for i in range(n):
        st = statuses[i]
        due = date(2026, 5, 24) + timedelta(days=int(RNG.integers(-120, 180)))
        supplier = SUPPLIERS[int(RNG.integers(0, len(SUPPLIERS)))]
        penalty = float(RNG.integers(0, 250_000)) if st in ("Breached", "At Risk") else 0.0
        rows.append(
            {
                "deliverable_id": f"OBL-{10001 + i}",
                "obligation_ref": f"SCH-2.{(i % 12) + 1}",
                "title": f"Deliverable obligation {(i % 40) + 1}",
                "status": st,
                "due_date": due,
                "supplier_name": supplier,
                "penalty_exposure_gbp": penalty,
                "created_ts": pd.Timestamp("2024-01-15") + pd.Timedelta(days=int(RNG.integers(0, 400))),
            }
        )
    return pd.DataFrame(rows)


def build_sla_performance() -> pd.DataFrame:
    """480 rows = 20 KPIs × 24 months; exactly 72 breaches total (~15%)."""
    slots = [(mi, ki) for mi in range(24) for ki in range(20)]
    RNG.shuffle(slots)
    breach_target = 72
    breach_set = set(slots[:breach_target])

    rows: list[dict] = []
    for mi, month_start in enumerate(_MONTHS_24):
        for ki, kpi in enumerate(KPI_NAMES):
            is_breach = (mi, ki) in breach_set
            compliance = float(RNG.uniform(82.0, 99.5)) if not is_breach else float(RNG.uniform(65.0, 79.0))
            supplier = SUPPLIERS[int(RNG.integers(0, len(SUPPLIERS)))]
            rows.append(
                {
                    "sla_record_id": str(uuid.uuid4()),
                    "kpi_name": kpi,
                    "period_date": month_start,
                    "is_breach": is_breach,
                    "compliance_pct": round(compliance, 2),
                    "breach_reason": "Below threshold" if is_breach else None,
                    "supplier_name": supplier,
                }
            )

    df = pd.DataFrame(rows)

    # Ensure current calendar month has several breaches (dashboard “this month”).
    last_mask = df["period_date"] == pd.Timestamp(_CURRENT_MONTH_START)
    need_here = 8
    cur_b = int(df.loc[last_mask, "is_breach"].sum())
    if cur_b < need_here:
        deficit = need_here - cur_b
        non_b_last = df.index[last_mask & (~df["is_breach"])].tolist()
        b_other = df.index[(~last_mask) & df["is_breach"]].tolist()
        RNG.shuffle(non_b_last)
        RNG.shuffle(b_other)
        for i in range(min(deficit, len(non_b_last), len(b_other))):
            df.loc[non_b_last[i], ["is_breach", "compliance_pct", "breach_reason"]] = (
                True,
                round(float(RNG.uniform(65.0, 79.0)), 2),
                "Below threshold",
            )
            df.loc[b_other[i], ["is_breach", "compliance_pct", "breach_reason"]] = (
                False,
                round(float(RNG.uniform(88.0, 99.0)), 2),
                None,
            )

    assert int(df["is_breach"].sum()) == breach_target
    return df


def build_supplier_performance() -> pd.DataFrame:
    """120 rows = 5 suppliers × 24 months; two suppliers average < 70."""
    rows = []
    for mi, month_start in enumerate(_MONTHS_24):
        for supplier in SUPPLIERS:
            if supplier in _LOW_SUPPLIERS:
                score = float(RNG.uniform(52.0, 69.5))
                band = "Amber"
            else:
                score = float(RNG.uniform(76.0, 96.0))
                band = "Green"
            rows.append(
                {
                    "supplier_record_id": str(uuid.uuid4()),
                    "supplier_name": supplier,
                    "period_date": month_start,
                    "overall_score": round(score, 1),
                    "rating_band": band,
                    "notes": None,
                }
            )
    return pd.DataFrame(rows)


def build_contract_monthly_metrics() -> pd.DataFrame:
    """24 monthly rows; compliance dips in months 19–22 (indices 18–21); latest ~88%."""
    rows = []
    for i, month_start in enumerate(_MONTHS_24):
        if 18 <= i <= 21:
            compliance = float(RNG.uniform(87.2, 89.1))
        elif i > 21:
            compliance = float(RNG.uniform(87.5, 89.5))
        else:
            compliance = float(RNG.uniform(91.5, 94.2))

        audit_day = date(month_start.year + (1 if month_start.month >= 6 else 0), 5, 24)
        rows.append(
            {
                "metrics_row_id": str(uuid.uuid4()),
                "period_date": month_start,
                "overall_sla_compliance": round(compliance, 2),
                "next_audit_date": audit_day,
                "open_deliverables_count": int(RNG.integers(18, 48)),
                "breaches_mtd_count": int(RNG.integers(0, 15)),
            }
        )

    df = pd.DataFrame(rows)
    # Latest month headline compliance near 88%
    last_ix = df.index[-1]
    df.loc[last_ix, "overall_sla_compliance"] = 88.2
    df.loc[last_ix, "next_audit_date"] = date(2026, 5, 24)
    return df


def validate_data(
    deliverables: pd.DataFrame | None = None,
    sla: pd.DataFrame | None = None,
    supplier: pd.DataFrame | None = None,
    metrics: pd.DataFrame | None = None,
) -> None:
    """Assert Phase 2 distributions (same checks as PLAN acceptance narrative)."""
    deliverables = deliverables if deliverables is not None else build_contract_deliverables()
    sla = sla if sla is not None else build_sla_performance()
    supplier = supplier if supplier is not None else build_supplier_performance()
    metrics = metrics if metrics is not None else build_contract_monthly_metrics()

    assert len(deliverables) == 200
    assert deliverables["deliverable_id"].notna().all()
    assert deliverables["status"].notna().all()

    assert len(sla) == 480
    assert sla["is_breach"].notna().all()
    breach_n = int(sla["is_breach"].sum())
    assert breach_n == 72, breach_n

    assert len(supplier) == 120
    avg_by = supplier.groupby("supplier_name")["overall_score"].mean()
    below_70 = int((avg_by < 70).sum())
    assert below_70 >= 2, avg_by

    assert len(metrics) == 24
    assert metrics["period_date"].is_monotonic_increasing
    dip = metrics.iloc[18:22]["overall_sla_compliance"].astype(float)
    baseline = metrics.iloc[8:16]["overall_sla_compliance"].astype(float)
    assert dip.mean() < baseline.mean()
    assert dip.mean() < 90.5


def build_all() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build all four tables (deterministic RNG seed)."""
    return (
        build_contract_deliverables(),
        build_sla_performance(),
        build_supplier_performance(),
        build_contract_monthly_metrics(),
    )


if __name__ == "__main__":
    validate_data()
    d, s, sp, m = build_all()
    print("validate_data OK")
    print(d.groupby("status").size())
    print("sla breaches", s["is_breach"].sum())
    print(sp.groupby("supplier_name")["overall_score"].mean())
    print(m.tail(6)[["period_date", "overall_sla_compliance"]])
