"""Supervisor — routes TfL executive questions to Genie (metrics) or RAG (contract text)."""

from __future__ import annotations

import re
from typing import Any, Literal

from use_cases.base_config import UseCaseConfig

from agents.genie_agent import GenieAgent
from agents.rag_agent import RAGAgent

RouteName = Literal["rag", "genie"]


def build_supervisor_instructions(cfg: UseCaseConfig) -> str:
    """System prompt for an Agent Bricks / hosted supervisor (Phase 4–5 integration)."""
    return f"""You are the Adaptive Leader Intelligence supervisor for {cfg.persona_name}, {cfg.persona_title}.

Domain: {cfg.domain_summary}

You route user messages to specialized tools:
- **Contract / governance / clauses** — obligations wording, penalties, reporting cadence, audits, change control, subcontractor rules. Use the knowledge-base tool for "what does the contract say", clauses, and procedural governance text.
- **Metrics and operational data** — SLA compliance %, breaches, supplier scores, counts, trends, comparisons, lists of deliverables or obligations from systems data. Use the data analytics (Genie) tool.

Persona: Address {cfg.persona_name} as a CTO; be concise, cite numbers when available, and surface delivery risk early.

If both contract language and numbers matter, call the knowledge tool first for clause context, then data analytics for thresholds, and synthesize one answer."""


# Strong phrase hints (lowercased)
_RAG_HINTS = (
    "what does the contract say",
    "does the contract say",
    "contract say about",
    "under the contract",
    "clause",
    "penalty clause",
    "penalties under",
    "governance",
    "audit requirements",
    "audit requirement",
    "change control",
    "reporting cadence",
    "reporting obligations",
    "subcontractor",
    "escalation procedure",
    "contractual obligation",
    "according to the contract",
)

_GENIE_HINTS = (
    "are we hitting",
    "sla compliance",
    "slas",
    "sla ",
    "breach",
    "breaches",
    "supplier score",
    "how many",
    "how much",
    "count ",
    "compare ",
    "comparison",
    "trend",
    "this month",
    "last month",
    "last period",
    "overall score",
    "which obligations",
    "which deliverables",
    "at risk",
    "show me",
    "list ",
    "top ",
    "average ",
    "avg ",
)


def classify_route(user_message: str) -> RouteName:
    """
    Keyword routing for demo reliability (hosted supervisor may use LLM tools instead).

    Prefer **RAG** for contract/governance language; **Genie** for metrics and operational lists.
    """
    t = user_message.lower().strip()

    rag_score = sum(1 for h in _RAG_HINTS if h in t)
    genie_score = sum(1 for h in _GENIE_HINTS if h in t)

    # Disambiguate "reporting obligations" (contract text) vs operational metrics
    if "reporting obligations" in t or "reporting obligation" in t:
        rag_score += 3

    if re.search(r"\b(which|how many|show|list)\b.*\b(at risk|breached|deliverable|obligation|supplier)\b", t):
        genie_score += 3

    if "why did compliance" in t or "why did" in t and "compliance" in t:
        # Trend explanation may cite contract + data; lean Genie for dip drivers from data
        genie_score += 2

    if genie_score > rag_score:
        return "genie"
    if rag_score > genie_score:
        return "rag"
    # Tie-break: short operational questions → Genie; otherwise RAG
    if any(w in t.split()[:4] for w in ("show", "how", "which", "count", "list")):
        return "genie"
    return "rag"


class SupervisorAgent:
    """Orchestrates RAG + Genie using ``classify_route`` (local, deterministic)."""

    def __init__(
        self,
        uc_config: UseCaseConfig,
        *,
        rag_agent: RAGAgent | None = None,
        genie_agent: GenieAgent | None = None,
    ) -> None:
        self._cfg = uc_config
        self.rag_agent = rag_agent or RAGAgent(uc_config)
        self.genie_agent = genie_agent or GenieAgent(uc_config)
        self.conversation_history: list[dict[str, Any]] = []

    def route_query(self, user_message: str) -> RouteName:
        return classify_route(user_message)

    def execute(self, user_message: str) -> dict[str, Any]:
        route = self.route_query(user_message)
        try:
            if route == "genie":
                result = self.genie_agent.query(user_message)
                result["routed_to"] = "Genie"
            else:
                result = self.rag_agent.query(user_message)
                result["routed_to"] = "RAG"

            self.conversation_history.append({"role": "user", "content": user_message, "route": route})
            self.conversation_history.append(
                {"role": "assistant", "content": result.get("answer", ""), "route": route}
            )
            result["route"] = route
            return result
        except Exception as e:
            return {"answer": f"Supervisor error: {e}", "error": str(e), "routed_to": "Error", "route": route}

    def clear_history(self) -> None:
        self.conversation_history.clear()
