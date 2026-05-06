"""Leader profile — UC-backed prompt weights with config fallback."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from databricks.sdk import WorkspaceClient

from dbx_sql import fetch_all, insert_batches, run_statement
from use_cases.base_config import UseCaseConfig

DECAY_PER_DAY = 0.95


def _parse_ts(val: str | None) -> datetime | None:
    if val is None or str(val).strip() == "":
        return None
    v = str(val).strip()
    try:
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        return datetime.fromisoformat(v)
    except ValueError:
        return None


class LeaderProfileAgent:
    """Reads/writes ``leader_profiles``; computes time-decayed ranking; falls back to ``UC_CONFIG`` offline."""

    def __init__(
        self,
        cfg: UseCaseConfig,
        *,
        warehouse_id: str | None = None,
        profile: str | None = None,
    ):
        self._cfg = cfg
        self._warehouse_id = (warehouse_id or os.environ.get("DATABRICKS_WAREHOUSE_ID") or "").strip()
        self._profile = profile or os.environ.get("DATABRICKS_CONFIG_PROFILE", "azure_demo")
        self._client: WorkspaceClient | None = None
        if self._warehouse_id:
            try:
                if os.environ.get("DATABRICKS_APP_NAME") or os.environ.get("DATABRICKS_RUNTIME_VERSION"):
                    self._client = WorkspaceClient()
                else:
                    self._client = WorkspaceClient(profile=self._profile)
            except Exception:
                self._client = None

    @property
    def uc_available(self) -> bool:
        return self._client is not None and bool(self._warehouse_id)

    def _table_fqn(self) -> str:
        return f"`{self._cfg.uc_catalog}`.`{self._cfg.uc_schema}`.`leader_profiles`"

    def _effective_weight(self, ask_count: int, last_ts: datetime | None) -> float:
        now = datetime.now(timezone.utc)
        if last_ts is None:
            days = 180.0
        else:
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)
            days = max(0.0, (now - last_ts).total_seconds() / 86400.0)
        return float(ask_count) * (DECAY_PER_DAY**days)

    def _load_rows_raw(self) -> list[list[Any]]:
        assert self._client and self._warehouse_id
        pid = self._cfg.persona_id.replace("'", "''")
        uid = self._cfg.use_case_id.replace("'", "''")
        sql = f"""
SELECT profile_id, persona_id, use_case_id, question_text, category, ask_count, last_asked_ts, source, created_ts
FROM {self._table_fqn()}
WHERE persona_id = '{pid}' AND use_case_id = '{uid}'
""".strip()
        return fetch_all(self._client, self._warehouse_id, sql)

    def _count_rows(self) -> int:
        assert self._client and self._warehouse_id
        pid = self._cfg.persona_id.replace("'", "''")
        uid = self._cfg.use_case_id.replace("'", "''")
        sql = f"SELECT COUNT(*) FROM {self._table_fqn()} WHERE persona_id = '{pid}' AND use_case_id = '{uid}'"
        rows = fetch_all(self._client, self._warehouse_id, sql)
        return int(rows[0][0]) if rows else 0

    def _seed_from_config_sql(self) -> None:
        """Insert starter rows when table is empty (same distribution as seed_leader_profile)."""
        from sample_data.leader_profile_seed import build_seed_dataframe

        assert self._client and self._warehouse_id
        df = build_seed_dataframe(self._cfg)
        for stmt in insert_batches(
            self._cfg.uc_catalog,
            self._cfg.uc_schema,
            "leader_profiles",
            (
                "profile_id",
                "persona_id",
                "use_case_id",
                "question_text",
                "category",
                "ask_count",
                "last_asked_ts",
                "source",
                "created_ts",
            ),
            df,
            batch_rows=50,
        ):
            run_statement(self._client, self._warehouse_id, stmt)

    def _fallback_questions(self, n: int) -> list[dict[str, Any]]:
        out = []
        for sq in sorted(self._cfg.sample_questions, key=lambda x: x.weight, reverse=True)[:n]:
            out.append(
                {
                    "question": sq.question,
                    "category": sq.category,
                    "weight": float(sq.weight),
                    "ask_count": max(1, sq.weight // 10),
                    "source": "config",
                }
            )
        return out

    def get_top_questions(self, n: int = 5) -> list[dict[str, Any]]:
        if not self.uc_available:
            return self._fallback_questions(n)

        try:
            if self._count_rows() == 0:
                self._seed_from_config_sql()
            raw = self._load_rows_raw()
        except Exception:
            return self._fallback_questions(n)

        if not raw:
            return self._fallback_questions(n)

        ranked: list[dict[str, Any]] = []
        for row in raw:
            profile_id = row[0]
            question_text = row[3]
            category = row[4] or ""
            ask_count = int(row[5])
            last_ts = _parse_ts(row[6] if len(row) > 6 else None)
            source = row[7] if len(row) > 7 else "user"
            eff = self._effective_weight(ask_count, last_ts)
            ranked.append(
                {
                    "question": question_text,
                    "category": category,
                    "weight": round(eff, 4),
                    "ask_count": ask_count,
                    "profile_id": profile_id,
                    "source": source,
                }
            )
        ranked.sort(key=lambda x: x["weight"], reverse=True)
        return ranked[:n]

    def log_question(self, question: str, *, category: str | None = None) -> None:
        """Record a user question — increments ask_count or inserts a new row."""
        q = question.strip()
        if not q:
            return
        if not self.uc_available:
            return

        pid_lit = self._cfg.persona_id.replace("'", "''")
        uc_lit = self._cfg.use_case_id.replace("'", "''")
        q_lit = q.replace("'", "''")
        cat_trim = (category or "").strip()
        cat_sql = "CAST(NULL AS STRING)" if not cat_trim else "'" + cat_trim.replace("'", "''") + "'"
        new_id = uuid.uuid4().hex

        merge_sql = f"""
MERGE INTO {self._table_fqn()} AS t
USING (
  SELECT
    '{new_id}' AS profile_id,
    '{pid_lit}' AS persona_id,
    '{uc_lit}' AS use_case_id,
    '{q_lit}' AS question_text,
    {cat_sql} AS category,
    CAST(CURRENT_TIMESTAMP() AS TIMESTAMP) AS ts
) AS s
ON t.persona_id = s.persona_id AND t.question_text = s.question_text
WHEN MATCHED THEN UPDATE SET
  ask_count = t.ask_count + 1,
  last_asked_ts = s.ts,
  source = 'user'
WHEN NOT MATCHED THEN INSERT (profile_id, persona_id, use_case_id, question_text, category, ask_count, last_asked_ts, source, created_ts)
VALUES (
  s.profile_id,
  s.persona_id,
  s.use_case_id,
  s.question_text,
  s.category,
  1,
  s.ts,
  'user',
  s.ts
)
""".strip()

        try:
            assert self._client and self._warehouse_id
            run_statement(self._client, self._warehouse_id, merge_sql)
        except Exception:
            pass
