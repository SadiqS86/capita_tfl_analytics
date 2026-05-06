"""RAG agent — Databricks Knowledge Assistant over UC volume PDFs."""

from __future__ import annotations

import os
from typing import Any

import requests
from databricks.sdk import WorkspaceClient

from use_cases.base_config import UseCaseConfig


class RAGAgent:
    """Invokes the Knowledge Assistant serving endpoint (same pattern as ``agent_bricks_demo``)."""

    def __init__(self, uc_config: UseCaseConfig, *, profile: str | None = None) -> None:
        self._cfg = uc_config
        self._profile = profile or os.environ.get("DATABRICKS_CONFIG_PROFILE", "azure_demo")
        if os.environ.get("DATABRICKS_APP_NAME") or os.environ.get("DATABRICKS_RUNTIME_VERSION"):
            self.w = WorkspaceClient()
        else:
            self.w = WorkspaceClient(profile=self._profile)

    @property
    def assistant_resource_name(self) -> str:
        return (self._cfg.knowledge_assistant_id or "").strip()

    def query(self, question: str) -> dict[str, Any]:
        if not self.assistant_resource_name:
            return {
                "answer": "Knowledge Assistant is not configured. Run "
                "`scripts/setup_knowledge_assistant.py` or set KNOWLEDGE_ASSISTANT_RESOURCE_NAME.",
                "sources": [],
                "agent": "RAG",
                "error": "missing_knowledge_assistant_id",
            }

        try:
            ka = self.w.knowledge_assistants.get_knowledge_assistant(name=self.assistant_resource_name)
            endpoint_name = ka.endpoint_name
            if not endpoint_name:
                return {
                    "answer": "Knowledge Assistant has no endpoint yet; wait for provisioning to finish.",
                    "sources": [],
                    "agent": "RAG",
                    "error": "no_endpoint",
                }

            cfg = self.w.config
            host = cfg.host
            token = cfg.token or cfg.authenticate()
            url = f"{host}/serving-endpoints/{endpoint_name}/invocations"
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            payload = {"input": [{"role": "user", "content": question}]}
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            response_json = response.json()

            answer = "No response generated."
            sources: list[dict[str, Any]] = []
            for output in response_json.get("output", []):
                if isinstance(output, dict) and output.get("type") == "message":
                    for item in output.get("content", []):
                        if item.get("type") == "output_text":
                            answer = item.get("text", answer)
                            sources = self._sources_from_annotations(item.get("annotations", []))
                            break

            return {
                "answer": answer,
                "sources": sources,
                "agent": "RAG",
                "raw_response": response_json,
            }
        except Exception as e:
            err = str(e)
            if "not ready" in err.lower() or "syncing" in err.lower():
                return {
                    "answer": "Knowledge Assistant is still ingesting documents; try again shortly.",
                    "sources": [],
                    "agent": "RAG",
                    "error": "syncing",
                }
            return {
                "answer": f"Error querying Knowledge Assistant: {err}",
                "sources": [],
                "agent": "RAG",
                "error": err,
            }

    def _sources_from_annotations(self, annotations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for ann in annotations:
            if ann.get("type") != "url_citation":
                continue
            url = ann.get("url", "")
            document = "Unknown"
            page: int | None = None
            if "/Volumes/" in url or "/knowledge_base/" in url:
                parts = url.split("/")
                if parts:
                    document = parts[-1].split("#")[0]
                if "#page=" in url:
                    try:
                        page = int(url.split("#page=")[1].split(":")[0])
                    except ValueError:
                        page = None
            out.append({"document": document, "page": page, "url": url})
        return out

    def format_response(self, result: dict[str, Any]) -> str:
        lines = [f"**Answer:**\n{result.get('answer', '')}"]
        src = result.get("sources") or []
        if src:
            lines.append("\n**Sources:**")
            for i, s in enumerate(src, 1):
                doc = s.get("document", "Unknown")
                pg = s.get("page")
                lines.append(f"{i}. {doc}" + (f", page {pg}" if pg is not None else ""))
        return "\n".join(lines)
