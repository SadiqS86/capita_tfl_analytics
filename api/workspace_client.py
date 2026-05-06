"""Databricks WorkspaceClient — local profile vs Databricks App runtime."""

from __future__ import annotations

import os

from databricks.sdk import WorkspaceClient


def _in_databricks_app() -> bool:
    return bool(
        os.environ.get("DATABRICKS_APP_NAME")
        or os.environ.get("DATABRICKS_RUNTIME_VERSION")
        or os.environ.get("DATABRICKS_SERVERLESS")
    )


def get_workspace_client() -> WorkspaceClient:
    """In Apps, use ambient credentials; locally use ``DATABRICKS_CONFIG_PROFILE`` (default ``azure_demo``)."""
    if _in_databricks_app():
        return WorkspaceClient()
    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE", "azure_demo")
    return WorkspaceClient(profile=profile)
