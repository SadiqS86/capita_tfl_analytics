"""Synthetic leader_profiles rows aligned with ``UC_CONFIG.sample_questions``."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pandas as pd

from use_cases.base_config import UseCaseConfig


def build_seed_dataframe(cfg: UseCaseConfig) -> pd.DataFrame:
    """10 rows with staggered ask history (higher ``sample_questions.weight`` → higher ask_count)."""
    base = datetime(2026, 5, 6, 9, 0, 0, tzinfo=timezone.utc)
    rows = []
    for i, sq in enumerate(cfg.sample_questions):
        ask_count = max(2, min(48, sq.weight // 2))
        last = base - timedelta(days=i * 4, hours=i * 2)
        rows.append(
            {
                "profile_id": uuid.uuid4().hex,
                "persona_id": cfg.persona_id,
                "use_case_id": cfg.use_case_id,
                "question_text": sq.question,
                "category": sq.category,
                "ask_count": ask_count,
                "last_asked_ts": pd.Timestamp(last),
                "source": "seed",
                "created_ts": pd.Timestamp(base - timedelta(days=30)),
            }
        )
    return pd.DataFrame(rows)
