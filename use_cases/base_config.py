from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
class KPIDefinition:
    """Single dashboard KPI backed by a Databricks SQL expression."""

    kpi_id: str
    label: str
    unit: str
    icon: str
    sql_query: str
    description: str = ""


@dataclass(frozen=True)
class SampleQuestion:
    """Weighted suggestion surfaced to the leader (used with profile learning later)."""

    question: str
    category: str
    weight: int


@dataclass(frozen=True)
class UseCaseConfig:
    """Typed bundle for one demo use case — personas, UC pointers, KPIs, seed prompts."""

    use_case_id: str
    persona_id: str
    persona_name: str
    persona_title: str
    domain_summary: str
    uc_catalog: str
    uc_schema: str
    genie_space_id: str
    knowledge_assistant_id: str
    supervisor_endpoint: str
    kpis: Tuple[KPIDefinition, ...]
    sample_questions: Tuple[SampleQuestion, ...]
    runtime_notes: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def uc_fqn_prefix(self) -> str:
        """Fully-qualified catalog.schema prefix for SQL (Databricks three-part names)."""
        return f"`{self.uc_catalog}`.`{self.uc_schema}`"
