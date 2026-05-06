#!/usr/bin/env python3
"""Generate four synthetic TfL / Capita contract PDFs for the Knowledge Assistant."""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB_DIR = ROOT / "use_cases" / "capita_tfl" / "knowledge_base"


def _build_contract_overview() -> list[str]:
    return [
        "Transport for London (TfL) — Managed Services Agreement",
        "",
        "Parties: TfL as client; Capita plc as prime contractor for technology and data services.",
        "Term: Multi-year agreement with staged milestones aligned to TfL digital roadmap.",
        "Scope: Service delivery, subcontractor coordination, SLA-backed operations, and executive reporting.",
        "Commercial summary: Value band and indexation per Schedule A; audit rights retained by TfL.",
        "",
        "Key schedules: SLA Framework (20 KPIs), Governance & Compliance, Supplier Management, Change Control.",
    ]


def _build_sla_framework() -> list[str]:
    lines = [
        "SLA Framework — Measurement Methodology",
        "",
        "Each KPI has a defined measurement window, data source, and breach threshold.",
        "Breaches are recorded monthly; repeated breaches trigger escalation per Governance schedule.",
        "",
        "Illustrative KPI families (not exhaustive): availability, incident resolution, ",
        "data freshness, security incident response, milestone delivery, and customer-impact events.",
        "",
        "Targets are expressed as minimum thresholds or maximum allowable downtime depending on KPI type.",
        "Overall SLA compliance rolls up from monthly KPI results across all in-scope services.",
    ]
    return lines


def _build_supplier_obligations() -> list[str]:
    return [
        "Supplier & Subcontractor Obligations",
        "",
        "Capita remains accountable to TfL for subcontractor performance.",
        "Subcontractors must meet the same SLA and security obligations flow-down.",
        "",
        "Penalty clauses: Material breaches may attract service credits and remediation plans ",
        "as defined in the commercial schedules; persistent breach triggers executive escalation.",
        "",
        "Escalation: Tier 1 operational review; Tier 2 programme steering; Tier 3 executive joint ",
        "review with TfL contract leadership.",
    ]


def _build_governance() -> list[str]:
    return [
        "Governance, Compliance & Reporting",
        "",
        "Reporting cadence: Monthly performance pack; quarterly executive review; annual assurance alignment.",
        "Change control: Material scope or dependency changes require documented approval under the change framework.",
        "",
        "Audit: TfL may request evidence packs for controls, data lineage, and subcontractor assurance.",
        "Data protection: Processing aligns with applicable regulations and TfL security standards.",
        "",
        "Records retention and evidence of SLA calculations must be maintained for the audit window stated in the agreement.",
    ]


def _write_pdf(path: Path, title: str, body_lines: list[str]) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    y = height - 72
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, y, title)
    y -= 28
    c.setFont("Helvetica", 11)
    for line in body_lines:
        if y < 72:
            c.showPage()
            y = height - 72
            c.setFont("Helvetica", 11)
        c.drawString(72, y, line[:120])
        y -= 14
    c.save()


def main() -> None:
    p = argparse.ArgumentParser(description="Generate TfL contract PDFs for Knowledge Assistant ingestion.")
    p.add_argument("--output-dir", type=Path, default=KB_DIR)
    args = p.parse_args()
    out = args.output_dir
    specs = [
        ("contract_overview.pdf", "Contract Overview", _build_contract_overview()),
        ("sla_framework.pdf", "SLA Framework", _build_sla_framework()),
        ("supplier_obligations.pdf", "Supplier Obligations", _build_supplier_obligations()),
        ("governance_compliance.pdf", "Governance & Compliance", _build_governance()),
    ]
    for fname, title, lines in specs:
        dest = out / fname
        _write_pdf(dest, title, lines)
        print(f"Wrote {dest}")
    print(f"Done. Upload via scripts/setup_knowledge_assistant.py ({len(specs)} files).")


if __name__ == "__main__":
    main()
