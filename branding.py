"""Resolve display branding (app name + logo) for the Databricks App.

Source priority (highest first):

1. Env vars: ``APP_NAME``, ``APP_LOGO_URL``, ``APP_LOGO_URL_DARK``
2. ``runtime_resources.json`` keys: ``app_name``, ``app_logo_url``, ``app_logo_url_dark``
3. Hard defaults (empty strings — UI hides the logo block when empty)

The logo URL can be either:
- A relative path served by the frontend bundle (e.g. ``/logo.png`` →
  ``frontend/public/logo.png`` after build), or
- An absolute URL to an external asset (e.g. an S3/CDN URL).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_DEFAULT_APP_NAME = "Capita TfL Analytics"


def _runtime_json() -> dict:
    p = Path(__file__).resolve().parent / "runtime_resources.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resolve(env_key: str, json_key: str, default: str = "") -> str:
    v = os.environ.get(env_key, "").strip()
    if v:
        return v
    raw = _runtime_json().get(json_key)
    if raw is None:
        return default
    return str(raw).strip() or default


def get_branding() -> dict[str, str]:
    """Return the resolved branding dict (always present, possibly empty values)."""
    light = _resolve("APP_LOGO_URL", "app_logo_url")
    dark = _resolve("APP_LOGO_URL_DARK", "app_logo_url_dark") or light
    return {
        "app_name": _resolve("APP_NAME", "app_name", _DEFAULT_APP_NAME),
        "app_logo_url": light,
        "app_logo_url_dark": dark,
    }
