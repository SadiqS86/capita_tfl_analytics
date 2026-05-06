"""Lakebase Postgres connection + chat persistence helpers.

Auth model:
- The App service principal calls the Databricks Database REST API to mint an
  OAuth token for the Lakebase endpoint (rotated every ~1h).
- We use that token as the Postgres password; the user is the SP UUID.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

logger = logging.getLogger(__name__)


_DEFAULT_USE_CASE = os.environ.get("USE_CASE", "capita_tfl")
_TOKEN_TTL_SEC = 50 * 60  # rotate ~10 min before the 1h expiry

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()
_cached_token: tuple[str, float] | None = None


def _lakebase_user() -> str:
    """Return the username Lakebase expects.

    On a Databricks App, the SDK injects DATABRICKS_CLIENT_ID = the SP UUID,
    which is the role we created in Postgres. Locally fall back to the
    workspace user email (developer's own account).
    """
    user = (os.environ.get("DATABRICKS_CLIENT_ID") or "").strip()
    if user:
        return user
    return (os.environ.get("DATABRICKS_USER") or "").strip()


def _generate_database_token() -> str:
    """Mint a short-lived Postgres password via Databricks Database API."""
    from databricks.sdk import WorkspaceClient

    if os.environ.get("DATABRICKS_APP_NAME") or os.environ.get("DATABRICKS_RUNTIME_VERSION"):
        w = WorkspaceClient()
    else:
        w = WorkspaceClient(profile=os.environ.get("DATABRICKS_CONFIG_PROFILE", "azure_demo"))

    project = os.environ.get("LAKEBASE_PROJECT", "capita-tfl-analytics-pg")
    branch = os.environ.get("LAKEBASE_BRANCH", "production")
    endpoint_id = os.environ.get("LAKEBASE_ENDPOINT_ID", "primary")
    name = f"projects/{project}/branches/{branch}/endpoints/{endpoint_id}"

    api = getattr(w, "postgres", None) or getattr(w, "database", None)
    if api is None:
        raise RuntimeError("Databricks SDK does not expose postgres/database API")

    if hasattr(api, "generate_database_credential"):
        cred = api.generate_database_credential(name=name)
    else:  # SDK fallback via raw API call
        resp = w.api_client.do(
            "POST",
            f"/api/2.0/postgres/{name}:generateDatabaseCredential",
        )
        cred = resp

    token = getattr(cred, "token", None) or (cred.get("token") if isinstance(cred, dict) else None)
    if not token:
        raise RuntimeError(f"No token in generate_database_credential response: {cred!r}")
    return token


def _current_token() -> str:
    global _cached_token
    now = time.time()
    if _cached_token and now < _cached_token[1]:
        return _cached_token[0]
    tok = _generate_database_token()
    _cached_token = (tok, now + _TOKEN_TTL_SEC)
    return tok


def _conninfo() -> str:
    host = os.environ.get("LAKEBASE_HOST", "").strip()
    db = os.environ.get("LAKEBASE_DATABASE", "chat_memory").strip()
    user = _lakebase_user()
    if not host or not user:
        raise RuntimeError(
            "Lakebase env not configured: LAKEBASE_HOST or DATABRICKS_CLIENT_ID/USER missing"
        )
    return (
        f"host={host} port=5432 dbname={db} user={user} "
        f"password={_current_token()} sslmode=require connect_timeout=10"
    )


def _make_pool() -> ConnectionPool:
    return ConnectionPool(
        conninfo=_conninfo,
        min_size=0,
        max_size=4,
        timeout=15,
        kwargs={"row_factory": dict_row},
        open=True,
    )


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = _make_pool()
    return _pool


@contextmanager
def conn() -> Iterator[psycopg.Connection]:
    pool = get_pool()
    with pool.connection() as c:
        yield c


def is_enabled() -> bool:
    return bool(os.environ.get("LAKEBASE_HOST")) and bool(_lakebase_user())


def latest_conversation_id(user_id: str, use_case_id: str = _DEFAULT_USE_CASE) -> str | None:
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT conversation_id::text AS conversation_id
            FROM conversations
            WHERE user_id = %s AND use_case_id = %s
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (user_id, use_case_id),
        )
        row = cur.fetchone()
        return row["conversation_id"] if row else None


def create_conversation(user_id: str, use_case_id: str = _DEFAULT_USE_CASE, title: str | None = None) -> str:
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            INSERT INTO conversations (user_id, use_case_id, title)
            VALUES (%s, %s, %s)
            RETURNING conversation_id::text AS conversation_id
            """,
            (user_id, use_case_id, title),
        )
        c.commit()
        row = cur.fetchone()
        return row["conversation_id"]


def get_or_create_active_conversation(user_id: str, use_case_id: str = _DEFAULT_USE_CASE) -> str:
    cid = latest_conversation_id(user_id, use_case_id)
    if cid:
        return cid
    return create_conversation(user_id, use_case_id)


def append_message(
    conversation_id: str,
    role: str,
    content: str,
    *,
    routed_to: str | None = None,
    sql_text: str | None = None,
    elapsed_ms: int | None = None,
) -> None:
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            INSERT INTO messages (conversation_id, role, content, routed_to, sql_text, elapsed_ms)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (conversation_id, role, content, routed_to, sql_text, elapsed_ms),
        )
        cur.execute(
            "UPDATE conversations SET updated_at = now() WHERE conversation_id = %s",
            (conversation_id,),
        )
        c.commit()


def load_messages(conversation_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT role, content, routed_to, elapsed_ms,
                   to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS created_at
            FROM messages
            WHERE conversation_id = %s
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (conversation_id, limit),
        )
        return list(cur.fetchall())


def recent_history(conversation_id: str, max_turns: int = 12) -> list[dict[str, str]]:
    """Return the last ``max_turns`` messages as [{role, content}, ...] in chronological order."""
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT role, content
            FROM (
                SELECT role, content, created_at
                FROM messages
                WHERE conversation_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            ) t
            ORDER BY created_at ASC
            """,
            (conversation_id, max_turns),
        )
        return [{"role": r["role"], "content": r["content"]} for r in cur.fetchall()]
