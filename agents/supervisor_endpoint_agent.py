"""Calls the deployed supervisor agent serving endpoint (Agent Bricks).

This is what the user sees in the AI Playground — full multi-tool agent with
persona instructions, NOT the local keyword-routing ``SupervisorAgent``.
"""

from __future__ import annotations

import os
from typing import Any

import requests
from databricks.sdk import WorkspaceClient

from use_cases.base_config import UseCaseConfig


class SupervisorEndpointAgent:
    """POSTs to ``serving-endpoints/<supervisor_endpoint>/invocations``."""

    def __init__(self, uc_config: UseCaseConfig, *, profile: str | None = None) -> None:
        self._cfg = uc_config
        self._profile = profile or os.environ.get("DATABRICKS_CONFIG_PROFILE", "azure_demo")
        if os.environ.get("DATABRICKS_APP_NAME") or os.environ.get("DATABRICKS_RUNTIME_VERSION"):
            self.w = WorkspaceClient()
        else:
            self.w = WorkspaceClient(profile=self._profile)

    @property
    def endpoint_name(self) -> str:
        return (self._cfg.supervisor_endpoint or "").strip()

    def query(self, question: str) -> dict[str, Any]:
        if not self.endpoint_name:
            return {
                "answer": "Supervisor endpoint is not configured. Run "
                "`scripts/setup_supervisor_serving.py` or set "
                "`runtime_resources.json:supervisor_endpoint`.",
                "agent": "Supervisor",
                "route": "supervisor",
                "routed_to": "Supervisor",
                "error": "missing_supervisor_endpoint",
            }

        try:
            cfg = self.w.config
            host = cfg.host
            token = cfg.token or cfg.authenticate()
            if isinstance(token, dict):
                token = token.get("Authorization", "").replace("Bearer ", "")

            url = f"{host}/serving-endpoints/{self.endpoint_name}/invocations"
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            payload = {"input": [{"role": "user", "content": question}]}

            response = requests.post(url, headers=headers, json=payload, timeout=180)
            response.raise_for_status()
            response_json = response.json()

            answer = self._extract_text(response_json) or "No response generated."

            return {
                "answer": answer,
                "agent": "Supervisor",
                "route": "supervisor",
                "routed_to": "Supervisor",
                "raw_response": response_json,
            }
        except Exception as exc:
            return {
                "answer": f"Error querying Supervisor: {exc}",
                "agent": "Supervisor",
                "route": "supervisor",
                "routed_to": "Supervisor",
                "error": str(exc),
            }

    def _extract_text(self, response_json: dict[str, Any]) -> str:
        """Pull final human-readable text from Agent Bricks responses.

        Agent responses contain multiple message blocks: tool-use announcements,
        tool results, and finally the synthesis. We want only the **last**
        ``output_text`` (the agent's final answer to the user) — earlier blocks
        like "I'll check our SLA performance..." are intermediate reasoning.
        """
        outputs = response_json.get("output", [])
        text_blocks: list[str] = []
        for o in outputs:
            if not isinstance(o, dict):
                continue
            if o.get("type") != "message":
                continue
            if o.get("role") and o.get("role") != "assistant":
                continue
            for item in o.get("content", []) or []:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "output_text":
                    text = (item.get("text") or "").strip()
                    if text:
                        text_blocks.append(text)

        if text_blocks:
            return text_blocks[-1] if len(text_blocks) > 1 else text_blocks[0]

        choices = response_json.get("choices") or []
        for c in choices:
            msg = (c or {}).get("message") or {}
            if msg.get("content"):
                return str(msg["content"])

        if isinstance(response_json.get("output_text"), str):
            return response_json["output_text"]

        return ""
