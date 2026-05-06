from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    mode: Literal["supervisor", "genie", "rag"] = "supervisor"
    history: list[ChatTurn] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    routed_to: str | None = None
    route: str | None = None
    suggested_followups: list[str] = Field(default_factory=list)
    sql: str | None = None
    sources: list[dict[str, Any]] | None = None


class KPIValue(BaseModel):
    kpi_id: str
    label: str
    unit: str
    icon: str
    value: float | str | None
    error: str | None = None


class BootstrapResponse(BaseModel):
    persona_name: str
    persona_title: str
    domain_summary: str
    use_case_id: str
