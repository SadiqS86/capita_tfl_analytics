"""Generate contextual follow-up questions using a fast foundation model.

Used after each chat answer so the suggestion panel reflects what was just
discussed (e.g. drilling into a specific supplier the agent mentioned).
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import requests
from databricks.sdk import WorkspaceClient

from use_cases.base_config import UseCaseConfig

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "databricks-claude-haiku-4-5"

CATEGORIES = ("SLA", "Obligations", "Trends", "Suppliers", "Risk", "Contract")


def _system_prompt(cfg: UseCaseConfig, preferred_category: str | None) -> str:
    base = (
        f"You are a copilot helping {cfg.persona_name}, {cfg.persona_title}, "
        f"explore '{cfg.domain_summary}'. After each exchange you suggest 5 "
        "short, specific follow-up questions a senior leader would naturally "
        "ask next. Each question must be ≤90 chars, action-oriented, and "
        "categorised as one of: " + ", ".join(CATEGORIES) + ". "
        "Each suggestion must be a logical follow-on from the most recent answer — "
        "drill-downs, comparisons, root causes, or remediation actions are ideal. "
        "Avoid repeating questions already asked in the conversation."
    )
    if preferred_category:
        pc = preferred_category.strip()
        base += (
            f" The user's last action focused on the '{pc}' category, so AT LEAST 3 of 5 "
            f"suggestions MUST have c='{pc}' and dig deeper into that area. "
            "The remaining 1–2 may use a different category if they offer a clear cross-cut."
        )
    return base + (
        " Respond with ONLY a JSON array (no prose, no markdown fencing) of "
        "5 objects: [{\"q\": \"…\", \"c\": \"SLA\"}, …]"
    )


class SuggestionGenerator:
    """Calls a foundation model serving endpoint to produce structured follow-ups."""

    def __init__(self, uc_config: UseCaseConfig, *, endpoint: str | None = None) -> None:
        self._cfg = uc_config
        self._endpoint = endpoint or os.environ.get("SUGGESTIONS_ENDPOINT", DEFAULT_ENDPOINT)
        if os.environ.get("DATABRICKS_APP_NAME") or os.environ.get("DATABRICKS_RUNTIME_VERSION"):
            self.w = WorkspaceClient()
        else:
            self.w = WorkspaceClient(profile=os.environ.get("DATABRICKS_CONFIG_PROFILE", "azure_demo"))

    def generate(
        self,
        history: list[dict[str, str]],
        n: int = 5,
        preferred_category: str | None = None,
    ) -> list[dict[str, Any]]:
        if not history:
            return []
        try:
            cfg = self.w.config
            host = cfg.host
            token = cfg.token or cfg.authenticate()
            if isinstance(token, dict):
                token = token.get("Authorization", "").replace("Bearer ", "")

            url = f"{host}/serving-endpoints/{self._endpoint}/invocations"
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

            messages: list[dict[str, str]] = [
                {"role": "system", "content": _system_prompt(self._cfg, preferred_category)}
            ]
            for turn in history[-8:]:
                role = turn.get("role")
                content = (turn.get("content") or "").strip()
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content[:1500]})
            cat_hint = (
                f" Bias at least 3 toward category '{preferred_category}'."
                if preferred_category
                else ""
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Based on the conversation so far, return ONLY the JSON array of "
                        f"{n} follow-up questions in the format described.{cat_hint}"
                    ),
                }
            )

            payload = {"messages": messages, "max_tokens": 400, "temperature": 0.3}
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()

            text = self._extract_text(data) or ""
            items = self._parse_items(text)
            if not items:
                return []
            return [
                {
                    "question": str(it.get("q") or it.get("question") or "").strip(),
                    "category": self._normalize_category(it.get("c") or it.get("category")),
                    "weight": 0,
                    "source": "contextual",
                }
                for it in items
                if (it.get("q") or it.get("question"))
            ][:n]
        except Exception as exc:
            logger.warning("SuggestionGenerator.generate failed: %s", exc)
            return []

    def _normalize_category(self, c: Any) -> str:
        if not c:
            return "Insights"
        s = str(c).strip()
        for cat in CATEGORIES:
            if cat.lower() == s.lower():
                return cat
        return s.title()[:24]

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

    def _parse_items(self, text: str) -> list[dict[str, Any]]:
        s = text.strip()
        if s.startswith("```"):
            s = re.sub(r"^```(?:json)?\s*", "", s)
            s = re.sub(r"\s*```\s*$", "", s)
        try:
            obj = json.loads(s)
            if isinstance(obj, list):
                return [x for x in obj if isinstance(x, dict)]
            if isinstance(obj, dict):
                if isinstance(obj.get("items"), list):
                    return [x for x in obj["items"] if isinstance(x, dict)]
                if isinstance(obj.get("questions"), list):
                    return [x for x in obj["questions"] if isinstance(x, dict)]
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
