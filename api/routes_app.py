"""REST API for chat, KPIs, suggestions — wired to UC, Genie, KA, supervisor."""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from databricks.sdk import WorkspaceClient
from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse

from agents.genie_agent import GenieAgent
from agents.leader_profile_agent import LeaderProfileAgent
from agents.rag_agent import RAGAgent
from agents.supervisor import SupervisorAgent, classify_route
from api.schemas import BootstrapResponse, ChatRequest, ChatResponse, KPIValue
from api.workspace_client import get_workspace_client
from config import UC_CONFIG
from dbx_sql import fetch_all

router = APIRouter()


_ROUTE_LABELS = {
    "genie": "Genie (operational data)",
    "rag": "Knowledge Assistant (contracts)",
}

_STAGE_MESSAGES = {
    "genie": [
        (0.0, "Routing to Genie…"),
        (0.5, "Generating SQL with Genie…"),
        (3.0, "Running query on warehouse…"),
        (8.0, "Analysing results…"),
        (15.0, "Still working — large result sets can take a moment…"),
    ],
    "rag": [
        (0.0, "Routing to Knowledge Assistant…"),
        (0.5, "Searching contract documents…"),
        (3.0, "Synthesising answer…"),
        (10.0, "Still working — long contracts take a moment…"),
    ],
}


def _sse(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


def _warehouse_id() -> str:
    return (os.environ.get("DATABRICKS_WAREHOUSE_ID") or "").strip()


def _suggested_followups(user_question: str, n: int = 3) -> list[str]:
    qlow = user_question.strip().lower()
    out: list[str] = []
    for sq in UC_CONFIG.sample_questions:
        if sq.question.strip().lower() == qlow:
            continue
        out.append(sq.question)
        if len(out) >= n:
            break
    return out[:n]


def _run_sql_scalar(client: WorkspaceClient, warehouse_id: str, sql: str) -> Any | None:
    rows = fetch_all(client, warehouse_id, sql.strip())
    if not rows or not rows[0]:
        return None
    return rows[0][0]


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "use_case": UC_CONFIG.use_case_id}


@router.get("/bootstrap", response_model=BootstrapResponse)
def bootstrap() -> BootstrapResponse:
    return BootstrapResponse(
        persona_name=UC_CONFIG.persona_name,
        persona_title=UC_CONFIG.persona_title,
        domain_summary=UC_CONFIG.domain_summary,
        use_case_id=UC_CONFIG.use_case_id,
    )


@router.get("/suggestions")
def suggestions() -> dict[str, Any]:
    lp = LeaderProfileAgent(UC_CONFIG, warehouse_id=_warehouse_id() or None)
    rows = lp.get_top_questions(5)
    return {"items": rows}


@router.get("/kpis", response_model=list[KPIValue])
def kpis() -> list[KPIValue]:
    wid = _warehouse_id()
    if not wid:
        return [
            KPIValue(
                kpi_id=k.kpi_id,
                label=k.label,
                unit=k.unit,
                icon=k.icon,
                value=None,
                error="DATABRICKS_WAREHOUSE_ID not set",
            )
            for k in UC_CONFIG.kpis
        ]

    client = get_workspace_client()
    out: list[KPIValue] = []
    for k in UC_CONFIG.kpis:
        try:
            raw = _run_sql_scalar(client, wid, k.sql_query)
            if raw is None:
                val = None
            elif isinstance(raw, (int, float)):
                val = float(raw)
            else:
                val = str(raw)
            out.append(
                KPIValue(kpi_id=k.kpi_id, label=k.label, unit=k.unit, icon=k.icon, value=val, error=None)
            )
        except Exception as e:
            out.append(
                KPIValue(
                    kpi_id=k.kpi_id,
                    label=k.label,
                    unit=k.unit,
                    icon=k.icon,
                    value=None,
                    error=str(e),
                )
            )
    return out


@router.get("/dashboard/charts")
def dashboard_charts() -> dict[str, Any]:
    """Series for dashboard charts (optional — fails soft without warehouse)."""
    wid = _warehouse_id()
    if not wid:
        return {"compliance_trend": [], "breach_breakdown": [], "error": "no_warehouse"}

    c = UC_CONFIG.uc_catalog.replace("'", "")
    s = UC_CONFIG.uc_schema.replace("'", "")
    client = get_workspace_client()

    compliance_sql = f"""
SELECT date_format(period_date, 'MMM yyyy') AS period_month, overall_sla_compliance AS compliance
FROM `{c}`.`{s}`.`contract_monthly_metrics`
ORDER BY period_date DESC
LIMIT 12
""".strip()

    breach_sql = f"""
SELECT kpi_name, COUNT(*) AS cnt
FROM `{c}`.`{s}`.`sla_performance`
WHERE is_breach = true
  AND period_date >= date_sub(current_date(), 60)
GROUP BY kpi_name
ORDER BY cnt DESC
LIMIT 8
""".strip()

    try:
        trend_rows = fetch_all(client, wid, compliance_sql)
        compliance_trend = [
            {"month": str(r[0]), "compliance": float(r[1]) if r[1] is not None else None}
            for r in reversed(trend_rows)
        ]
    except Exception:
        compliance_trend = []

    try:
        breach_rows = fetch_all(client, wid, breach_sql)
        breach_breakdown = [{"name": str(r[0]), "count": int(r[1])} for r in breach_rows]
    except Exception:
        breach_breakdown = []

    return {"compliance_trend": compliance_trend, "breach_breakdown": breach_breakdown}


def _log_question_task(question: str) -> None:
    try:
        lp = LeaderProfileAgent(UC_CONFIG, warehouse_id=_warehouse_id() or None)
        lp.log_question(question.strip())
    except Exception:
        pass


@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(body: ChatRequest, background_tasks: BackgroundTasks) -> ChatResponse:
    background_tasks.add_task(_log_question_task, body.message)

    mode = body.mode
    msg = body.message.strip()
    followups = _suggested_followups(msg)

    if mode == "genie":
        agent = GenieAgent(UC_CONFIG)
        r = agent.query(msg)
        return ChatResponse(
            answer=str(r.get("answer") or ""),
            routed_to=r.get("agent"),
            route="genie",
            suggested_followups=followups,
            sql=r.get("sql"),
        )

    if mode == "rag":
        agent = RAGAgent(UC_CONFIG)
        r = agent.query(msg)
        return ChatResponse(
            answer=str(r.get("answer") or ""),
            routed_to=r.get("agent"),
            route="rag",
            suggested_followups=followups,
            sources=r.get("sources"),
        )

    sup = SupervisorAgent(UC_CONFIG)
    r = sup.execute(msg)
    return ChatResponse(
        answer=str(r.get("answer") or ""),
        routed_to=r.get("routed_to"),
        route=r.get("route"),
        suggested_followups=followups,
        sql=r.get("sql"),
        sources=r.get("sources"),
    )


@router.post("/chat/stream")
async def chat_stream(body: ChatRequest, background_tasks: BackgroundTasks) -> StreamingResponse:
    """Server-Sent Events: emit route, progressive status, then final answer.

    Does not stream LLM tokens (Genie/KA are not token-stream APIs), but gives
    the user near-instant visibility into what the system is doing — large
    perceived latency improvement over a single blocking POST /chat.
    """
    background_tasks.add_task(_log_question_task, body.message)

    msg = body.message.strip()
    mode = body.mode
    followups = _suggested_followups(msg)

    if mode == "genie":
        route = "genie"
    elif mode == "rag":
        route = "rag"
    else:
        route = classify_route(msg)

    async def event_stream():
        yield _sse("start", {"message": msg, "route": route, "label": _ROUTE_LABELS.get(route, route)})
        await asyncio.sleep(0)

        loop = asyncio.get_event_loop()

        def _run() -> dict[str, Any]:
            if route == "genie":
                return GenieAgent(UC_CONFIG).query(msg)
            return RAGAgent(UC_CONFIG).query(msg)

        worker = loop.run_in_executor(None, _run)

        started_at = time.time()
        stages = list(_STAGE_MESSAGES.get(route, [(0.0, "Working…")]))
        next_stage_idx = 0

        while not worker.done():
            elapsed = time.time() - started_at

            while next_stage_idx < len(stages) and stages[next_stage_idx][0] <= elapsed:
                _, label = stages[next_stage_idx]
                yield _sse("status", {"label": label, "elapsed_ms": int(elapsed * 1000)})
                next_stage_idx += 1

            try:
                await asyncio.wait_for(asyncio.shield(worker), timeout=0.5)
            except asyncio.TimeoutError:
                yield _sse("heartbeat", {"elapsed_ms": int(elapsed * 1000)})

        try:
            result = worker.result()
        except Exception as exc:
            yield _sse("error", {"message": str(exc)})
            yield _sse("done", {})
            return

        payload = {
            "answer": str(result.get("answer") or ""),
            "routed_to": result.get("agent") or _ROUTE_LABELS.get(route, route),
            "route": route,
            "sql": result.get("sql"),
            "sources": result.get("sources") or [],
            "suggested_followups": followups,
            "elapsed_ms": int((time.time() - started_at) * 1000),
        }
        yield _sse("answer", payload)
        yield _sse("done", {})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
