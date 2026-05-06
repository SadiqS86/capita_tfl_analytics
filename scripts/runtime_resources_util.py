"""Load and merge ``runtime_resources.json`` at the project root."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_runtime_resources(path: Path | None = None) -> dict:
    p = path or (project_root() / "runtime_resources.json")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def merge_runtime_resources(updates: dict, *, path: Path | None = None) -> Path:
    """Merge ``updates`` into JSON file; preserve existing keys not overwritten."""
    p = path or (project_root() / "runtime_resources.json")
    base = load_runtime_resources(p)
    base.update({k: v for k, v in updates.items() if v is not None})
    base["updated_at"] = datetime.now(timezone.utc).isoformat()
    p.write_text(json.dumps(base, indent=2), encoding="utf-8")
    return p
