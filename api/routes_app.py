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

import db
from agents.genie_agent import GenieAgent
from agents.leader_profile_agent import LeaderProfileAgent
from agents.rag_agent import RAGAgent
from agents.supervisor_endpoint_agent import SupervisorEndpointAgent
from api.schemas import BootstrapResponse, ChatRequest, ChatResponse, KPIValue
from api.workspace_client import get_workspace_client
from config import UC_CONFIG
from dbx_sql import fetch_all

DEMO_USER_ID = os.environ.get("DEMO_USER_ID", "adam")

router = APIRouter()


_ROUTE_LABELS = {
    "supervisor": "Supervisor agent",
    "genie": "Genie (operational data)",
    "rag": "Knowledge Assistant (contracts)",
}

_STAGE_MESSAGES = {
    "supervisor": [
        (0.0, "Routing to Supervisor agent…"),
        (0.5, "Supervisor reviewing your question…"),
        (3.0, "Calling tools (Genie / Knowledge Assistant)…"),
        (8.0, "Synthesising executive answer…"),
        (15.0, "Still working — multi-tool reasoning can take a moment…"),
    ],
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


@router.get("/conversation/current")
def current_conversation() -> dict[str, Any]:
    """Return the latest conversation (id + messages) for the demo user.

    Used by the React app on load to rehydrate the chat from Lakebase.
    Returns ``{enabled: false}`` when Lakebase env isn't configured.
    """
    if not db.is_enabled():
        return {"enabled": False, "conversation_id": None, "messages": []}
    try:
        conv_id = db.latest_conversation_id(DEMO_USER_ID, UC_CONFIG.use_case_id)
        if not conv_id:
            return {"enabled": True, "conversation_id": None, "messages": []}
        return {
            "enabled": True,
            "conversation_id": conv_id,
            "messages": db.load_messages(conv_id, limit=200),
        }
    except Exception as exc:
        return {"enabled": True, "conversation_id": None, "messages": [], "error": str(exc)}


@router.post("/conversation/new")
def start_new_conversation() -> dict[str, Any]:
    """Create a new empty conversation; subsequent chats append to it."""
    if not db.is_enabled():
        return {"enabled": False, "conversation_id": None}
    try:
        conv_id = db.create_conversation(DEMO_USER_ID, UC_CONFIG.use_case_id)
        return {"enabled": True, "conversation_id": conv_id}
    except Exception as exc:
        return {"enabled": True, "conversation_id": None, "error": str(exc)}


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

    sup = SupervisorEndpointAgent(UC_CONFIG)
    r = sup.query(msg, history=[t.model_dump() for t in body.history])
    return ChatResponse(
        answer=str(r.get("answer") or ""),
        routed_to=r.get("routed_to") or "Supervisor",
        route="supervisor",
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
        route = "supervisor"

    conv_id: str | None = None
    history: list[dict[str, str]] = [t.model_dump() for t in body.history]
    if db.is_enabled():
        try:
            conv_id = db.get_or_create_active_conversation(DEMO_USER_ID, UC_CONFIG.use_case_id)
            history = db.recent_history(conv_id, max_turns=12)
            db.append_message(conv_id, "user", msg)
        except Exception as exc:
            conv_id = None
            print(f"[chat/stream] db.persist user msg failed: {exc}")

    async def event_stream():
        yield _sse(
            "start",
            {
                "message": msg,
                "route": route,
                "label": _ROUTE_LABELS.get(route, route),
                "conversation_id": conv_id,
            },
        )
        await asyncio.sleep(0)

        loop = asyncio.get_event_loop()

        def _run() -> dict[str, Any]:
            if route == "genie":
                return GenieAgent(UC_CONFIG).query(msg)
            if route == "rag":
                return RAGAgent(UC_CONFIG).query(msg)
            return SupervisorEndpointAgent(UC_CONFIG).query(msg, history=history)

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

        elapsed_ms = int((time.time() - started_at) * 1000)
        answer_text = str(result.get("answer") or "")
        payload = {
            "answer": answer_text,
            "routed_to": result.get("agent") or _ROUTE_LABELS.get(route, route),
            "route": route,
            "sql": result.get("sql"),
            "sources": result.get("sources") or [],
            "suggested_followups": followups,
            "elapsed_ms": elapsed_ms,
            "conversation_id": conv_id,
        }
        if conv_id and answer_text:
            try:
                db.append_message(
                    conv_id,
                    "assistant",
                    answer_text,
                    routed_to=str(payload["routed_to"]) if payload["routed_to"] else None,
                    sql_text=str(payload["sql"]) if payload["sql"] else None,
                    elapsed_ms=elapsed_ms,
                )
            except Exception as exc:
                print(f"[chat/stream] db.persist assistant msg failed: {exc}")
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
