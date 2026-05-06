"""Resolve display branding (app name + logo) for the Databricks App.

Source priority (highest first):

1. **Lakebase ``app_settings`` table** — runtime-mutable, no redeploy needed.
2. Env vars: ``APP_NAME``, ``APP_LOGO_URL``, ``APP_LOGO_URL_DARK``
3. ``runtime_resources.json`` keys: ``app_name``, ``app_logo_url``, ``app_logo_url_dark``
4. Hard defaults (empty strings — UI hides the logo block when empty)

A 30-second in-process cache avoids hitting Lakebase on every API call;
``invalidate_cache()`` is called by the write endpoint so saves appear
immediately.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

_DEFAULT_APP_NAME = "Capita TfL Analytics"
_CACHE_TTL_SEC = 30

_cache: dict[str, Any] | None = None
_cache_ts: float = 0.0
_cache_lock = threading.Lock()


def _runtime_json() -> dict:
    p = Path(__file__).resolve().parent / "runtime_resources.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _from_lakebase() -> dict[str, str]:
    """Read app_settings rows. Lazy import keeps module loadable when DB is off."""
    try:
        import db  # local import to avoid hard dependency at import time

        if not db.is_enabled():
            return {}
        return db.get_app_settings() or {}
    except Exception:
        return {}


def _resolve_one(
    settings: dict[str, str],
    settings_key: str,
    env_key: str,
    json_key: str,
    default: str = "",
) -> str:
    raw = (settings.get(settings_key) or "").strip()
    if raw:
        return raw
    v = os.environ.get(env_key, "").strip()
    if v:
        return v
    rj = _runtime_json().get(json_key)
    if rj is None:
        return default
    return str(rj).strip() or default


def get_branding() -> dict[str, str]:
    """Return the resolved branding dict (cached 30s; invalidate on write)."""
    global _cache, _cache_ts
    now = time.time()
    if _cache is not None and (now - _cache_ts) < _CACHE_TTL_SEC:
        return dict(_cache)

    with _cache_lock:
        if _cache is not None and (time.time() - _cache_ts) < _CACHE_TTL_SEC:
            return dict(_cache)

        settings = _from_lakebase()
        light = _resolve_one(settings, "app_logo_url", "APP_LOGO_URL", "app_logo_url")
        dark = _resolve_one(settings, "app_logo_url_dark", "APP_LOGO_URL_DARK", "app_logo_url_dark") or light
        out = {
            "app_name": _resolve_one(
                settings, "app_name", "APP_NAME", "app_name", _DEFAULT_APP_NAME
            ),
            "app_logo_url": light,
            "app_logo_url_dark": dark,
        }
        _cache = out
        _cache_ts = time.time()
        return dict(out)


def invalidate_cache() -> None:
    """Drop the cached branding so the next call hits Lakebase fresh."""
    global _cache, _cache_ts
    with _cache_lock:
        _cache = None
        _cache_ts = 0.0
