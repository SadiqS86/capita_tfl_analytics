"""Build Genie ``serialized_space`` JSON (v2) for Capita TfL UC tables."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from use_cases.base_config import UseCaseConfig


def _hid() -> str:
    return uuid.uuid4().hex


ROOT = Path(__file__).resolve().parent


def _load_md(name: str) -> str:
    p = ROOT / "docs" / "genie_instructions" / name
    try:
        return p.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def build_space_dict(cfg: UseCaseConfig, *, catalog: str | None = None, schema: str | None = None) -> dict[str, Any]:
    cat = catalog or cfg.uc_catalog
    sch = schema or cfg.uc_schema

    def fq(table: str) -> str:
        return f"{cat}.{sch}.{table}"

    tables_meta = sorted(
        [
            (
                "contract_deliverables",
                "TfL contract obligations and deliverables with status, due dates, suppliers, penalty exposure.",
            ),
            (
                "sla_performance",
                "Monthly SLA KPI measurements including breaches and compliance percentages.",
            ),
            (
                "supplier_performance",
                "Monthly supplier scorecards (0–100) and rating bands.",
            ),
            (
                "contract_monthly_metrics",
                "Monthly roll-up: overall SLA compliance %, next audit date, breach counts.",
            ),
        ],
        key=lambda item: fq(item[0]),
    )

    sample_questions = [{"id": _hid(), "question": [sq.question]} for sq in cfg.sample_questions]

    text_body = _load_md("01_text_instructions.md") or (
        "Capita TfL contract analytics. Prefer Unity Catalog tables in "
        f"{cat}.{sch}. Use monthly metrics for headline SLA %; use sla_performance for KPI-level breaches; "
        "use contract_deliverables for obligations and risk."
    )
    text_instructions = [{"id": _hid(), "content": [text_body]}]

    example_sqls = sorted(
        _example_question_sqls(cat, sch),
        key=lambda item: item["id"],
    )

    join_specs = sorted(
        [
        {
            "id": _hid(),
            "left": {"identifier": fq("contract_deliverables"), "alias": "d"},
            "right": {"identifier": fq("supplier_performance"), "alias": "sp"},
            "sql": [
                "`d`.`supplier_name` = `sp`.`supplier_name`",
                "--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_ONE--",
            ],
            "comment": ["Join deliverables to supplier monthly scores by supplier name."],
        },
        {
            "id": _hid(),
            "left": {"identifier": fq("sla_performance"), "alias": "sla"},
            "right": {"identifier": fq("contract_monthly_metrics"), "alias": "mm"},
            "sql": [
                "DATE_TRUNC('month', `sla`.`period_date`) = `mm`.`period_date`",
                "--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_ONE--",
            ],
            "comment": ["Align SLA detail rows to monthly contract metrics by calendar month."],
        },
        ],
        key=lambda item: item["id"],
    )

    return {
        "version": 2,
        "config": {"sample_questions": sample_questions},
        "data_sources": {
            "tables": [{"identifier": fq(name), "description": [desc]} for name, desc in tables_meta]
        },
        "instructions": {
            "text_instructions": text_instructions,
            "example_question_sqls": example_sqls,
            "join_specs": join_specs,
        },
    }


def _example_question_sqls(catalog: str, schema: str) -> list[dict[str, Any]]:
    """Eight curated examples (namespaced to catalog.schema)."""
    c, s = catalog, schema
    examples: list[tuple[str, list[str]]] = [
        (
            "Are we hitting our SLAs this month?",
            [
                f"SELECT ROUND(MAX(m.overall_sla_compliance), 2) AS pct\n",
                f"FROM `{c}`.`{s}`.`contract_monthly_metrics` AS m\n",
                "WHERE m.period_date = (SELECT MAX(period_date) FROM "
                f"`{c}`.`{s}`.`contract_monthly_metrics`)",
            ],
        ),
        (
            "Which obligations are at risk?",
            [
                f"SELECT deliverable_id, title, status, due_date, supplier_name\n",
                f"FROM `{c}`.`{s}`.`contract_deliverables`\n",
                "WHERE LOWER(TRIM(status)) IN ('at risk', 'at_risk')\n",
                "ORDER BY due_date ASC NULLS LAST\n",
                "LIMIT 50",
            ],
        ),
        (
            "How does SLA compliance compare this month vs last month?",
            [
                "WITH x AS (\n",
                f"  SELECT period_date, overall_sla_compliance\n",
                f"  FROM `{c}`.`{s}`.`contract_monthly_metrics`\n",
                "  ORDER BY period_date DESC\n",
                "  LIMIT 2\n",
                ")\n",
                "SELECT period_date, overall_sla_compliance FROM x ORDER BY period_date DESC",
            ],
        ),
        (
            "How many SLA breaches occurred this month?",
            [
                "SELECT COUNT(*) AS breach_count\n",
                f"FROM `{c}`.`{s}`.`sla_performance`\n",
                "WHERE is_breach = true\n",
                "  AND YEAR(period_date) = YEAR(CURRENT_DATE())\n",
                "  AND MONTH(period_date) = MONTH(CURRENT_DATE())",
            ],
        ),
        (
            "Which suppliers average below 70 points?",
            [
                "SELECT supplier_name, ROUND(AVG(overall_score), 2) AS avg_score\n",
                f"FROM `{c}`.`{s}`.`supplier_performance`\n",
                "GROUP BY supplier_name\n",
                "HAVING AVG(overall_score) < 70\n",
                "ORDER BY avg_score ASC",
            ],
        ),
        (
            "Show breach counts by KPI for the last 30 days",
            [
                "SELECT kpi_name, COUNT(*) AS breaches\n",
                f"FROM `{c}`.`{s}`.`sla_performance`\n",
                "WHERE is_breach = true\n",
                "  AND period_date >= DATE_ADD(CURRENT_DATE(), -30)\n",
                "GROUP BY kpi_name\n",
                "ORDER BY breaches DESC",
            ],
        ),
        (
            "What is overall SLA compliance trend over the last 6 months?",
            [
                "SELECT period_date, overall_sla_compliance\n",
                f"FROM `{c}`.`{s}`.`contract_monthly_metrics`\n",
                "ORDER BY period_date DESC\n",
                "LIMIT 6",
            ],
        ),
        (
            "List open deliverables due in the next 14 days",
            [
                "SELECT deliverable_id, title, due_date, supplier_name\n",
                f"FROM `{c}`.`{s}`.`contract_deliverables`\n",
                "WHERE LOWER(TRIM(status)) = 'open'\n",
                "  AND due_date BETWEEN CURRENT_DATE() AND DATE_ADD(CURRENT_DATE(), 14)\n",
                "ORDER BY due_date ASC",
            ],
        ),
    ]

    return [{"id": _hid(), "question": [q], "sql": sql_lines} for q, sql_lines in examples]


def build_serialized_space_string(cfg: UseCaseConfig, *, catalog: str | None = None, schema: str | None = None) -> str:
    """Single JSON string for Genie API ``serialized_space`` field."""
    payload = build_space_dict(cfg, catalog=catalog, schema=schema)
    return json.dumps(payload, separators=(",", ":"))
