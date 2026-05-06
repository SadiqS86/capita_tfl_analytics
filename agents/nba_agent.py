"""NBAAgent — generate Next Best Actions grounded in rules + clauses (Phase 6b).

Pipeline:

1. ``ActionRulesAgent.get_matching_rules(data_context)`` → matched threshold rules
2. (Optional) ``RAGAgent.query`` for additional clause snippets — only when
   the conversation makes contract language relevant.
3. Foundation Model API (structured JSON output) generates 1–3 actions.
4. Validate every ``contract_ref`` was either present in a matched rule or in a
   retrieved clause — otherwise drop it (no hallucinated citations).

Each action has the schema::

    {
      "action": str,        # ≤180 chars
      "urgency": "Immediate" | "This Week" | "Monitor",
      "rationale": str,     # ≤220 chars, references rule/clause/data
      "owner_role": str,
      "contract_ref": str,
    }
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import requests
from databricks.sdk import WorkspaceClient

from agents.action_rules_agent import ActionRulesAgent
from use_cases.base_config import UseCaseConfig

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "databricks-claude-haiku-4-5"
URGENCIES = ("Immediate", "This Week", "Monitor")


class NBAAgent:
    """Generates structured Next Best Actions from matched rules + an answer summary."""

    def __init__(
        self,
        uc_config: UseCaseConfig,
        *,
        endpoint: str | None = None,
        action_rules_agent: ActionRulesAgent | None = None,
    ) -> None:
        self._cfg = uc_config
        self._endpoint = endpoint or os.environ.get("NBA_ENDPOINT", DEFAULT_ENDPOINT)
        self.rules_agent = action_rules_agent or ActionRulesAgent(uc_config)
        if os.environ.get("DATABRICKS_APP_NAME") or os.environ.get("DATABRICKS_RUNTIME_VERSION"):
            self.w = WorkspaceClient()
        else:
            self.w = WorkspaceClient(profile=os.environ.get("DATABRICKS_CONFIG_PROFILE", "azure_demo"))

    def generate(
        self,
        answer_text: str,
        data_context: dict[str, Any] | None = None,
        conversation: list[dict[str, str]] | None = None,
        extra_clauses: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return ``{actions, matched_rule_count, used_data_context, raw}``.

        - ``answer_text``: the assistant's last reply (or a synthesis of the conversation).
        - ``data_context``: dict of metric values for rule matching. If omitted,
          live KPIs from ``ActionRulesAgent.evaluate_live_kpis`` are used.
        - ``conversation``: optional ``[{role, content}, …]`` for richer LLM grounding.
        - ``extra_clauses``: optional already-retrieved clause snippets.
        """
        if data_context is None:
            metrics, matched_rules = self.rules_agent.evaluate_live_kpis()
            data_context = metrics
        else:
            matched_rules = self.rules_agent.get_matching_rules(data_context, max_per_metric=2)

        allowed_clause_refs = {
            (r.get("contract_ref") or "").strip()
            for r in matched_rules
            if r.get("contract_ref")
        }
        for cl in extra_clauses or []:
            allowed_clause_refs.add(cl.strip())

        try:
            actions_raw = self._call_llm(
                answer_text=answer_text,
                data_context=data_context,
                matched_rules=matched_rules,
                conversation=conversation or [],
                extra_clauses=extra_clauses or [],
            )
        except Exception as exc:
            logger.warning("NBA LLM call failed, using rule-fallback: %s", exc)
            actions_raw = self._fallback_from_rules(matched_rules)

        actions = self._validate_actions(actions_raw, allowed_clause_refs)
        if not actions:
            actions = self._fallback_from_rules(matched_rules)
            actions = self._validate_actions(actions, allowed_clause_refs, lenient=True)

        actions = self._cap_urgency_to_rules(actions, matched_rules)

        return {
            "actions": actions[:5],
            "matched_rule_count": len(matched_rules),
            "data_context": data_context,
        }

    def _cap_urgency_to_rules(
        self,
        actions: list[dict[str, Any]],
        matched_rules: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Prevent the LLM from escalating beyond what matched rules permit.

        If every matched rule is Monitor (healthy state), drop any non-Monitor
        actions and cap the result at a single Monitor item.
        """
        if not matched_rules:
            return []

        rule_urgencies = {(r.get("urgency") or "").strip() for r in matched_rules}
        if rule_urgencies <= {"Monitor"}:
            monitors = [a for a in actions if a.get("urgency") == "Monitor"]
            if not monitors:
                monitors = [
                    {**a, "urgency": "Monitor"} for a in actions
                ]
            return monitors[:1]

        # Otherwise: drop any urgency level that no matched rule actually has.
        return [a for a in actions if a.get("urgency") in rule_urgencies] or actions

    def _system_prompt(self) -> str:
        cfg = self._cfg
        return f"""You are the Next Best Action engine for {cfg.persona_name}, {cfg.persona_title} at Capita, focused on the TfL contract performance.

Your job: produce 1–3 grounded recommendations that {cfg.persona_name} can act on TODAY.

Hard rules:
- Output STRICTLY a JSON array (no markdown, no prose, no preamble).
- Each item is an object with keys: action, urgency, rationale, owner_role, contract_ref.
- "urgency" MUST be one of: "Immediate", "This Week", "Monitor".
- The urgency of each output action MUST equal the urgency of the matched rule it grounds in. NEVER escalate (e.g. a Monitor rule must produce a Monitor action). NEVER assign Immediate or This Week unless a matched rule with that exact urgency is provided.
- "contract_ref" MUST be copied verbatim from one of the provided matched rules or extra clauses. Never invent a clause.
- "rationale" MUST cite either a matched rule's threshold OR a clause snippet OR a number from the data context. Never give a naked recommendation.
- Keep "action" ≤180 chars and "rationale" ≤220 chars.
- If every matched rule is Monitor (data is healthy), return AT MOST 1 Monitor-level action — do not invent urgency.
- If no matched rules are provided, return [] (an empty array).
- Do not duplicate the assistant's existing answer text — the action must add a NEXT STEP."""

    def _user_prompt(
        self,
        answer_text: str,
        data_context: dict[str, Any],
        matched_rules: list[dict[str, Any]],
        conversation: list[dict[str, str]],
        extra_clauses: list[str],
    ) -> str:
        rule_lines = []
        for r in matched_rules:
            rule_lines.append(
                f"- [{r.get('urgency')}] metric={r.get('trigger_metric')} "
                f"condition={r.get('trigger_condition')} | "
                f"action_template={r.get('action_text')} | "
                f"owner={r.get('owner_role')} | clause={r.get('contract_ref')}"
            )
        rules_block = "\n".join(rule_lines) if rule_lines else "(no matched rules — generate one Monitor item or none)"

        clause_block = "\n".join(f"- {c}" for c in extra_clauses) if extra_clauses else "(none)"
        ctx_block = json.dumps(data_context, default=str, sort_keys=True)

        recent = ""
        if conversation:
            tail = []
            for turn in conversation[-6:]:
                role = turn.get("role")
                content = (turn.get("content") or "").strip()
                if role and content:
                    tail.append(f"{role.upper()}: {content[:600]}")
            recent = "\n".join(tail)

        return f"""ASSISTANT_ANSWER (most recent):
{answer_text.strip()[:2000]}

DATA_CONTEXT (current metric values):
{ctx_block}

MATCHED_RULES (only sources you may cite for contract_ref):
{rules_block}

EXTRA_CLAUSES (additional citable snippets):
{clause_block}

RECENT_CONVERSATION:
{recent or "(none)"}

Return ONLY the JSON array now."""

    def _call_llm(
        self,
        *,
        answer_text: str,
        data_context: dict[str, Any],
        matched_rules: list[dict[str, Any]],
        conversation: list[dict[str, str]],
        extra_clauses: list[str],
    ) -> list[dict[str, Any]]:
        cfg = self.w.config
        host = cfg.host
        token = cfg.token or cfg.authenticate()
        if isinstance(token, dict):
            token = token.get("Authorization", "").replace("Bearer ", "")

        url = f"{host}/serving-endpoints/{self._endpoint}/invocations"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        messages = [
            {"role": "system", "content": self._system_prompt()},
            {
                "role": "user",
                "content": self._user_prompt(
                    answer_text=answer_text,
                    data_context=data_context,
                    matched_rules=matched_rules,
                    conversation=conversation,
                    extra_clauses=extra_clauses,
                ),
            },
        ]
        payload = {"messages": messages, "max_tokens": 800, "temperature": 0.2}
        response = requests.post(url, headers=headers, json=payload, timeout=45)
        response.raise_for_status()
        return self._parse_actions(self._extract_text(response.json()))

    def _extract_text(self, response_json: dict[str, Any]) -> str:
        choices = response_json.get("choices") or []
        for c in choices:
            msg = (c or {}).get("message") or {}
            if msg.get("content"):
                return str(msg["content"])
        for o in response_json.get("output", []) or []:
            if isinstance(o, dict) and o.get("type") == "message":
                for item in o.get("content", []) or []:
                    if isinstance(item, dict) and item.get("type") == "output_text":
                        if item.get("text"):
                            return str(item["text"])
        if isinstance(response_json.get("output_text"), str):
            return response_json["output_text"]
        return ""

    def _parse_actions(self, text: str) -> list[dict[str, Any]]:
        s = (text or "").strip()
        if s.startswith("```"):
            s = re.sub(r"^```(?:json)?\s*", "", s)
            s = re.sub(r"\s*```\s*$", "", s)
        try:
            obj = json.loads(s)
            if isinstance(obj, list):
                return [x for x in obj if isinstance(x, dict)]
            if isinstance(obj, dict) and isinstance(obj.get("actions"), list):
                return [x for x in obj["actions"] if isinstance(x, dict)]
        except Exception:
            pass
        m = re.search(r"\[\s*{.*?}\s*]", s, re.DOTALL)
        if m:
            try:
                obj = json.loads(m.group(0))
                if isinstance(obj, list):
                    return [x for x in obj if isinstance(x, dict)]
            except Exception:
                pass
        return []

    def _validate_actions(
        self,
        actions: list[dict[str, Any]],
        allowed_clause_refs: set[str],
        lenient: bool = False,
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for a in actions:
            if not isinstance(a, dict):
                continue
            action = str(a.get("action") or "").strip()
            urgency = str(a.get("urgency") or "").strip()
            rationale = str(a.get("rationale") or "").strip()
            owner = str(a.get("owner_role") or "").strip()
            ref = str(a.get("contract_ref") or "").strip()
            if not action or not urgency:
                continue
            if urgency not in URGENCIES:
                u = urgency.lower()
                if u.startswith("immediate"):
                    urgency = "Immediate"
                elif "monitor" in u:
                    urgency = "Monitor"
                elif "week" in u:
                    urgency = "This Week"
                else:
                    continue
            if ref and not lenient and ref not in allowed_clause_refs:
                # Only allow refs we explicitly grounded with.
                ref_lower = ref.lower()
                fuzzy = any(ref_lower in (c or "").lower() or (c or "").lower() in ref_lower for c in allowed_clause_refs)
                if not fuzzy:
                    ref = ""
            out.append(
                {
                    "action": action[:200],
                    "urgency": urgency,
                    "rationale": rationale[:240] if rationale else f"Triggered by data context.",
                    "owner_role": owner or "Adam Searle",
                    "contract_ref": ref,
                }
            )

        urgency_order = {"Immediate": 0, "This Week": 1, "Monitor": 2}
        out.sort(key=lambda a: urgency_order.get(a.get("urgency", ""), 99))
        return out

    def _fallback_from_rules(self, matched_rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Deterministic fallback when the LLM call fails or returns nothing usable."""
        out: list[dict[str, Any]] = []
        for r in matched_rules[:3]:
            out.append(
                {
                    "action": r.get("action_text") or "",
                    "urgency": r.get("urgency") or "Monitor",
                    "rationale": (
                        f"Rule triggered: {r.get('trigger_metric')} {r.get('trigger_condition')}."
                    ),
                    "owner_role": r.get("owner_role") or "Adam Searle",
                    "contract_ref": r.get("contract_ref") or "",
                }
            )
        return out
