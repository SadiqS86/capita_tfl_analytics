"""Genie agent — natural language to SQL against UC tables via a Genie space."""

from __future__ import annotations

import os
import time
from typing import Any

from use_cases.base_config import UseCaseConfig


class GenieAgent:
    """Runs questions through Databricks Genie (``w.genie.start_conversation`` + poll)."""

    def __init__(
        self,
        uc_config: UseCaseConfig,
        *,
        profile: str | None = None,
        max_wait_s: int = 90,
        poll_s: float = 2.0,
    ) -> None:
        self._cfg = uc_config
        self._profile = profile or os.environ.get("DATABRICKS_CONFIG_PROFILE", "azure_demo")
        self._max_wait_s = max_wait_s
        self._poll_s = poll_s

    @property
    def space_id(self) -> str:
        return (self._cfg.genie_space_id or "").strip()

    def query(self, question: str) -> dict[str, Any]:
        if not self.space_id:
            return {
                "answer": "Genie space is not configured. Run Phase 3 "
                "`scripts/create_genie_space.py` or set GENIE_SPACE_ID / runtime_resources.json.",
                "sql": None,
                "data": None,
                "agent": "Genie",
                "error": "missing_genie_space_id",
            }

        try:
            from databricks.sdk import WorkspaceClient

            if os.environ.get("DATABRICKS_APP_NAME") or os.environ.get("DATABRICKS_RUNTIME_VERSION"):
                w = WorkspaceClient()
            else:
                w = WorkspaceClient(profile=self._profile)

            conversation = w.genie.start_conversation(space_id=self.space_id, content=question)
            conversation_id = conversation.conversation_id
            message_id = conversation.message_id

            deadline = time.time() + self._max_wait_s
            message = conversation
            while time.time() < deadline:
                message = w.genie.get_message(
                    space_id=self.space_id,
                    conversation_id=conversation_id,
                    message_id=message_id,
                )
                st = getattr(message, "status", None)
                if st is not None:
                    su = str(st).upper()
                    if su in ("COMPLETED", "FAILED"):
                        break
                time.sleep(self._poll_s)

            sql_queries: list[str] = []
            results_data: list[Any] = []

            attachments = getattr(message, "attachments", None) or []
            for attachment in attachments:
                q = getattr(attachment, "query", None)
                if q is not None and getattr(q, "query", None):
                    sql_queries.append(q.query)
                aid = getattr(attachment, "attachment_id", None)
                if aid:
                    try:
                        result = w.genie.get_message_attachment_query_result(
                            space_id=self.space_id,
                            conversation_id=conversation_id,
                            message_id=message_id,
                            attachment_id=aid,
                        )
                        if result and getattr(result, "statement_response", None):
                            results_data.append(result.statement_response)
                    except Exception:
                        pass

            answer_text = getattr(message, "content", None) or "No response generated."

            formatted = answer_text
            if results_data:
                formatted = self._format_statement_response(results_data[0])

            return {
                "answer": formatted,
                "sql": sql_queries[0] if sql_queries else None,
                "data": results_data[0] if results_data else None,
                "agent": "Genie",
                "conversation_id": conversation_id,
            }
        except Exception as e:
            return {
                "answer": f"Error querying Genie: {e}",
                "sql": None,
                "data": None,
                "agent": "Genie",
                "error": str(e),
            }

    def _format_statement_response(self, statement_response: Any) -> str:
        try:
            import pandas as pd

            data_array = None
            columns: list[str] = []
            if hasattr(statement_response, "result") and statement_response.result:
                result = statement_response.result
                if hasattr(result, "data_array"):
                    data_array = result.data_array
            if hasattr(statement_response, "manifest") and statement_response.manifest:
                sch = getattr(statement_response.manifest, "schema", None)
                if sch and getattr(sch, "columns", None):
                    columns = [col.name for col in sch.columns]

            if data_array:
                df = pd.DataFrame(data_array, columns=columns if columns else None)
                if df.empty:
                    return "No rows returned."
                if len(df) <= 20:
                    return f"\n{df.to_string(index=False)}\n\nTotal rows: {len(df)}"
                return f"{df.head(10).to_string(index=False)}\n\n... ({len(df)} rows total, showing first 10)"
            return "Query completed but no tabular data was attached."
        except Exception as e:
            return f"Could not format SQL results: {e}"
