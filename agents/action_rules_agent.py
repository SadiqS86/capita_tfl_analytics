"""ActionRulesAgent — query and match the ``action_rules`` Delta table (Phase 6a).

Loads active rules from Unity Catalog and evaluates configurable thresholds against
a dictionary of current metric values (the "data context"). Returns the rules
whose ``trigger_condition`` evaluates true.

The ``trigger_condition`` strings are intentionally human-readable (e.g. ``"< 90"``,
``">= 3"``, ``"= Breached"``) and parsed here with a small safe evaluator — never
``eval()``.
"""

from __future__ import annotations

import operator
import os
import re
from datetime import datetime, timezone
from typing import Any, Iterable

from databricks.sdk import WorkspaceClient

from dbx_sql import fetch_all
from use_cases.base_config import UseCaseConfig

# Map metric strings → comparable Python values when matching is enabled.
# Numerics convert via float(); enums (status/severity) match case-insensitive.
_NUMERIC_OPS = {
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    "<": operator.lt,
    "=": operator.eq,
}

_CONDITION_RX = re.compile(
    r"^\s*(>=|<=|==|!=|>|<|=)\s*(.+?)\s*$"
)


def _parse_condition(condition: str) -> tuple[str, str] | None:
    m = _CONDITION_RX.match(condition or "")
    if not m:
        return None
    return m.group(1), m.group(2).strip().strip("'\"")


def _coerce(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    s = str(value).strip()
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        return s


def _evaluate(condition: str, data_value: Any) -> bool:
    parsed = _parse_condition(condition)
    if not parsed:
        return False
    op_str, raw_target = parsed
    op_fn = _NUMERIC_OPS.get(op_str)
    if not op_fn:
        return False

    target = _coerce(raw_target)
    actual = _coerce(data_value)

    if isinstance(target, (int, float)) and isinstance(actual, (int, float)):
        return bool(op_fn(actual, target))
    if op_str in ("=", "==", "!="):
        a = str(actual).strip().lower() if actual is not None else ""
        t = str(target).strip().lower()
        return op_fn(a, t)
    return False


class ActionRulesAgent:
    """Loads active rules from UC and matches them against a metric context."""

    def __init__(
        self,
        cfg: UseCaseConfig,
        *,
        warehouse_id: str | None = None,
        profile: str | None = None,
    ) -> None:
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
        self._cache: list[dict[str, Any]] | None = None
        self._cache_ts: datetime | None = None

    @property
    def uc_available(self) -> bool:
        return self._client is not None and bool(self._warehouse_id)

    def _table_fqn(self) -> str:
        return f"`{self._cfg.uc_catalog}`.`{self._cfg.uc_schema}`.`action_rules`"

    def _load_active_rules(self, force: bool = False) -> list[dict[str, Any]]:
        if not self.uc_available:
            return []
        # 5-minute in-process cache
        now = datetime.now(timezone.utc)
        if (
            not force
            and self._cache is not None
            and self._cache_ts is not None
            and (now - self._cache_ts).total_seconds() < 300
        ):
            return self._cache

        sql = f"""
SELECT rule_id, trigger_metric, trigger_condition, urgency,
       action_text, owner_role, contract_ref
FROM {self._table_fqn()}
WHERE use_case_id = '{self._cfg.use_case_id.replace("'", "''")}'
  AND active = true
""".strip()

        try:
            rows = fetch_all(self._client, self._warehouse_id, sql)
        except Exception:
            return []

        result = [
            {
                "rule_id": r[0],
                "trigger_metric": r[1],
                "trigger_condition": r[2],
                "urgency": r[3],
                "action_text": r[4],
                "owner_role": r[5],
                "contract_ref": r[6],
            }
            for r in rows
        ]
        self._cache = result
        self._cache_ts = now
        return result

    def get_active_rules(self) -> list[dict[str, Any]]:
        """Return all active rules (no condition matching). Refreshes the cache."""
        return list(self._load_active_rules(force=True))

    def get_matching_rules(
        self,
        metrics: dict[str, Any],
        *,
        max_per_metric: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return rules whose ``trigger_condition`` matches a value in ``metrics``.

        ``metrics`` keys are ``trigger_metric`` identifiers (e.g.
        ``sla_compliance_pct: 87.2``). Matched rules are sorted Immediate →
        This Week → Monitor.
        """
        rules = self._load_active_rules()
        matched: list[dict[str, Any]] = []
        for rule in rules:
            metric_name = rule.get("trigger_metric")
            if not metric_name or metric_name not in metrics:
                continue
            if _evaluate(rule.get("trigger_condition", ""), metrics[metric_name]):
                matched.append(rule)

        urgency_order = {"Immediate": 0, "This Week": 1, "Monitor": 2}
        matched.sort(key=lambda r: urgency_order.get(r.get("urgency", ""), 99))

        if max_per_metric is not None and max_per_metric > 0:
            kept: list[dict[str, Any]] = []
            seen: dict[str, int] = {}
            for r in matched:
                m = r.get("trigger_metric") or ""
                if seen.get(m, 0) >= max_per_metric:
                    continue
                seen[m] = seen.get(m, 0) + 1
                kept.append(r)
            return kept

        return matched

    def evaluate_live_kpis(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Pull current metric values from UC and return ``(metrics, matched_rules)``.

        Used by the dashboard Priority Actions widget — purely data-driven, no
        conversation needed.
        """
        if not self.uc_available:
            return {}, []

        c = self._cfg.uc_catalog
        s = self._cfg.uc_schema

        sql = f"""
WITH latest_metrics AS (
  SELECT MAX(period_date) AS p FROM `{c}`.`{s}`.`contract_monthly_metrics`
),
latest_supplier AS (
  SELECT MAX(period_date) AS p FROM `{c}`.`{s}`.`supplier_performance`
),
sla_compliance AS (
  SELECT ROUND(MAX(overall_sla_compliance), 1) AS v
  FROM `{c}`.`{s}`.`contract_monthly_metrics`
  WHERE period_date = (SELECT p FROM latest_metrics)
),
breach_count AS (
  SELECT COUNT(*) AS v
  FROM `{c}`.`{s}`.`sla_performance`
  WHERE is_breach = true
    AND YEAR(period_date) = YEAR(CURRENT_DATE())
    AND MONTH(period_date) = MONTH(CURRENT_DATE())
),
breached_obligations AS (
  SELECT COUNT(*) AS v
  FROM `{c}`.`{s}`.`contract_deliverables`
  WHERE LOWER(TRIM(status)) = 'breached'
),
at_risk_obligations AS (
  SELECT COUNT(*) AS v
  FROM `{c}`.`{s}`.`contract_deliverables`
  WHERE LOWER(TRIM(status)) IN ('at risk', 'at_risk')
),
worst_supplier AS (
  SELECT ROUND(MIN(overall_score), 1) AS v
  FROM `{c}`.`{s}`.`supplier_performance`
  WHERE period_date = (SELECT p FROM latest_supplier)
),
days_audit AS (
  SELECT CAST(DATEDIFF(DAY, CURRENT_DATE(), MAX(next_audit_date)) AS INT) AS v
  FROM `{c}`.`{s}`.`contract_monthly_metrics`
  WHERE period_date = (SELECT p FROM latest_metrics)
    AND next_audit_date >= CURRENT_DATE()
)
SELECT
  (SELECT v FROM sla_compliance) AS sla_compliance_pct,
  (SELECT v FROM breach_count) AS sla_breaches_count,
  (SELECT v FROM breached_obligations) AS breached_obligations_count,
  (SELECT v FROM at_risk_obligations) AS at_risk_obligations_count,
  (SELECT v FROM worst_supplier) AS supplier_overall_score,
  (SELECT v FROM days_audit) AS days_to_next_audit
""".strip()

        try:
            rows = fetch_all(self._client, self._warehouse_id, sql)
        except Exception:
            return {}, []

        if not rows or not rows[0]:
            return {}, []

        r = rows[0]
        metrics: dict[str, Any] = {
            "sla_compliance_pct": _coerce(r[0]),
            "sla_breaches_count": _coerce(r[1]),
            "supplier_overall_score": _coerce(r[4]),
            "days_to_next_audit": _coerce(r[5]),
        }
        breached_n = _coerce(r[2]) or 0
        at_risk_n = _coerce(r[3]) or 0
        if isinstance(breached_n, (int, float)) and breached_n > 0:
            metrics["obligation_status"] = "Breached"
        elif isinstance(at_risk_n, (int, float)) and at_risk_n > 0:
            metrics["obligation_status"] = "At Risk"

        matched = self.get_matching_rules(metrics, max_per_metric=2)
        return metrics, matched
