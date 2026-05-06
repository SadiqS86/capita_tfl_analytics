"""Workspace-oriented defaults and USE_CASE selector for UC_CONFIG."""

from __future__ import annotations

import os

from use_cases.base_config import UseCaseConfig
from use_cases.capita_tfl.config import CONFIG as _CAPITA_TFL

_USE_CASE = os.environ.get("USE_CASE", "capita_tfl").strip().lower()

_REGISTRY: dict[str, UseCaseConfig] = {
    "capita_tfl": _CAPITA_TFL,
}

if _USE_CASE not in _REGISTRY:
    raise ValueError(f"Unknown USE_CASE: {_USE_CASE!r}")

UC_CONFIG: UseCaseConfig = _REGISTRY[_USE_CASE]
