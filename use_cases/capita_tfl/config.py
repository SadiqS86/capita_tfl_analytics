"""Capita TfL use case — Adam Searle (CTO) persona, KPIs, and prompt seeds.

Unity Catalog object names align with Phase 2 DDL (`sample_data/create_tfl_tables.sql`).
KPI SQL references columns added there (including `next_audit_date` on monthly metrics).

Set ``UC_CATALOG`` and ``UC_SCHEMA`` to match the workspace you deploy to (e.g. ``azure_demo``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from use_cases.base_config import KPIDefinition, SampleQuestion, UseCaseConfig


def _runtime_json() -> dict:
    root = Path(__file__).resolve().parents[2]
    p = root / "runtime_resources.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resolve_genie_space_id() -> str:
    env_id = os.environ.get("GENIE_SPACE_ID", "").strip()
    if env_id:
        return env_id
    return str(_runtime_json().get("genie_space_id") or "").strip()


def _normalize_knowledge_assistant_name(value: str) -> str:
    v = value.strip()
    if not v:
        return ""
    if v.startswith("knowledge-assistants/"):
        return v
    return f"knowledge-assistants/{v}"


def _resolve_knowledge_assistant_resource_name() -> str:
    env_v = os.environ.get("KNOWLEDGE_ASSISTANT_RESOURCE_NAME", "").strip()
    if env_v:
        return _normalize_knowledge_assistant_name(env_v)
    env_legacy = os.environ.get("KNOWLEDGE_ASSISTANT_ID", "").strip()
    if env_legacy:
        return _normalize_knowledge_assistant_name(env_legacy)
    data = _runtime_json()
    for key in ("knowledge_assistant_resource_name", "knowledge_assistant_id", "knowledge_assistant_name"):
        raw = data.get(key)
        if raw:
            return _normalize_knowledge_assistant_name(str(raw))
    return ""


def _resolve_supervisor_endpoint() -> str:
    env_v = os.environ.get("SUPERVISOR_ENDPOINT", "").strip()
    if env_v:
        return env_v
    return str(_runtime_json().get("supervisor_endpoint") or "").strip()


def _resolve_uc_knowledge_volume() -> str:
    return os.environ.get("UC_KNOWLEDGE_VOLUME", "tfl_contract_kb").strip() or "tfl_contract_kb"

_UC_CATALOG = os.environ.get("UC_CATALOG", "ss_kibbim_azure_stable")
_UC_SCHEMA = os.environ.get("UC_SCHEMA", "capita_tfl_demo")
_UC = f"`{_UC_CATALOG}`.`{_UC_SCHEMA}`"
_T_DEL = f"{_UC}.`contract_deliverables`"
_T_SLA = f"{_UC}.`sla_performance`"
_T_SUP = f"{_UC}.`supplier_performance`"
_T_MET = f"{_UC}.`contract_monthly_metrics`"

_KPIS: tuple[KPIDefinition, ...] = (
    KPIDefinition(
        kpi_id="overall_sla_compliance",
        label="Overall SLA Compliance",
        unit="%",
        icon="Activity",
        description="Latest month overall SLA compliance vs target.",
        sql_query=f"""
SELECT ROUND(MAX(m.overall_sla_compliance), 1) AS value
FROM {_T_MET} AS m
WHERE m.period_date = (SELECT MAX(period_date) FROM {_T_MET})
""".strip(),
    ),
    KPIDefinition(
        kpi_id="open_deliverables",
        label="Open Deliverables",
        unit="count",
        icon="FileText",
        description="Count of deliverables not yet complete.",
        sql_query=f"""
SELECT COUNT(*) AS value
FROM {_T_DEL}
WHERE LOWER(TRIM(status)) = 'open'
""".strip(),
    ),
    KPIDefinition(
        kpi_id="at_risk_obligations",
        label="At Risk Obligations",
        unit="count",
        icon="AlertTriangle",
        description="Deliverables flagged at risk.",
        sql_query=f"""
SELECT COUNT(*) AS value
FROM {_T_DEL}
WHERE LOWER(TRIM(status)) IN ('at risk', 'at_risk')
""".strip(),
    ),
    KPIDefinition(
        kpi_id="breaches_this_month",
        label="Breaches This Month",
        unit="count",
        icon="TrendingDown",
        description="SLA breach records in the current calendar month.",
        sql_query=f"""
SELECT COUNT(*) AS value
FROM {_T_SLA}
WHERE is_breach = true
  AND YEAR(period_date) = YEAR(CURRENT_DATE())
  AND MONTH(period_date) = MONTH(CURRENT_DATE())
""".strip(),
    ),
    KPIDefinition(
        kpi_id="avg_supplier_score",
        label="Avg Supplier Score",
        unit="points",
        icon="Users",
        description="Average overall supplier score for the latest period.",
        sql_query=f"""
SELECT ROUND(AVG(s.overall_score), 1) AS value
FROM {_T_SUP} AS s
WHERE s.period_date = (SELECT MAX(period_date) FROM {_T_SUP})
""".strip(),
    ),
    KPIDefinition(
        kpi_id="days_to_next_audit",
        label="Days to Next Audit",
        unit="days",
        icon="Calendar",
        description="Days from today to the next scheduled audit date on the latest metrics row.",
        sql_query=f"""
SELECT CAST(
  DATEDIFF(
    DAY,
    CURRENT_DATE(),
    MAX(m.next_audit_date)
  ) AS INT
) AS value
FROM {_T_MET} AS m
WHERE m.period_date = (SELECT MAX(period_date) FROM {_T_MET})
  AND m.next_audit_date >= CURRENT_DATE()
""".strip(),
    ),
)

_SAMPLE_QUESTIONS: tuple[SampleQuestion, ...] = (
    SampleQuestion(
        question="Are we hitting our SLAs this month?",
        category="SLA",
        weight=95,
    ),
    SampleQuestion(
        question="Which obligations are at risk?",
        category="Obligations",
        weight=88,
    ),
    SampleQuestion(
        question="How does performance compare to last period?",
        category="Trends",
        weight=82,
    ),
    SampleQuestion(
        question="What are the top 5 SLA breaches by impact?",
        category="SLA",
        weight=76,
    ),
    SampleQuestion(
        question="Which supplier is underperforming?",
        category="Suppliers",
        weight=71,
    ),
    SampleQuestion(
        question="How does SLA compliance compare this month vs last month?",
        category="SLA",
        weight=69,
    ),
    SampleQuestion(
        question="What are our reporting obligations under the contract?",
        category="Governance",
        weight=67,
    ),
    SampleQuestion(
        question="What is the penalty exposure on at-risk obligations?",
        category="Obligations",
        weight=64,
    ),
    SampleQuestion(
        question="Why did compliance drop in the last 3 months?",
        category="Trends",
        weight=61,
    ),
    SampleQuestion(
        question="Which deliverables are breached or at risk?",
        category="Obligations",
        weight=58,
    ),
)

CONFIG = UseCaseConfig(
    use_case_id="capita_tfl",
    persona_id="adam_searle_cto",
    persona_name="Adam Searle",
    persona_title="Chief Technology Officer, Capita",
    domain_summary=(
        "TfL contract performance — SLAs, deliverables, suppliers, and compliance "
        "for executive briefing."
    ),
    uc_catalog=_UC_CATALOG,
    uc_schema=_UC_SCHEMA,
    genie_space_id=_resolve_genie_space_id(),
    knowledge_assistant_id=_resolve_knowledge_assistant_resource_name(),
    supervisor_endpoint=_resolve_supervisor_endpoint(),
    kpis=_KPIS,
    sample_questions=_SAMPLE_QUESTIONS,
    runtime_notes=(
        "Populate genie_space_id (Phase 3), knowledge_assistant_resource_name and supervisor_endpoint "
        "(Phase 4) via scripts or runtime_resources.json / env vars.",
    ),
)


def uc_knowledge_volume_path() -> str:
    """Unity Catalog volume path for TfL contract PDFs (Knowledge Assistant files source)."""
    return f"/Volumes/{_UC_CATALOG}/{_UC_SCHEMA}/{_resolve_uc_knowledge_volume()}"
