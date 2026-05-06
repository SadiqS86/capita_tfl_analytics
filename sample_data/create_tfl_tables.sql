-- DDL_SPLIT
-- Unity Catalog Delta DDL for Capita / TfL demo (Phase 2).
-- Substitute __CATALOG__ and __SCHEMA__ before execution (see scripts/setup_uc.py).

-- DDL_SPLIT
CREATE TABLE IF NOT EXISTS `__CATALOG__`.`__SCHEMA__`.`contract_deliverables` (
  deliverable_id       STRING NOT NULL,
  obligation_ref       STRING NOT NULL,
  title                STRING NOT NULL,
  status               STRING NOT NULL COMMENT 'Complete | Open | At Risk | Breached',
  due_date             DATE,
  supplier_name        STRING,
  penalty_exposure_gbp DOUBLE,
  created_ts           TIMESTAMP NOT NULL
)
USING DELTA
COMMENT 'TfL contract deliverables / obligations';

-- DDL_SPLIT
CREATE TABLE IF NOT EXISTS `__CATALOG__`.`__SCHEMA__`.`sla_performance` (
  sla_record_id   STRING NOT NULL,
  kpi_name        STRING NOT NULL,
  period_date     DATE NOT NULL,
  is_breach       BOOLEAN NOT NULL,
  compliance_pct  DOUBLE NOT NULL,
  breach_reason   STRING,
  supplier_name   STRING
)
USING DELTA
COMMENT 'Monthly SLA KPI measurements (20 KPIs × history)';

-- DDL_SPLIT
CREATE TABLE IF NOT EXISTS `__CATALOG__`.`__SCHEMA__`.`supplier_performance` (
  supplier_record_id STRING NOT NULL,
  supplier_name      STRING NOT NULL,
  period_date        DATE NOT NULL,
  overall_score      DOUBLE NOT NULL COMMENT '0–100',
  rating_band        STRING NOT NULL COMMENT 'Green | Amber | Red',
  notes              STRING
)
USING DELTA
COMMENT 'Supplier scorecards by month';

-- DDL_SPLIT
CREATE TABLE IF NOT EXISTS `__CATALOG__`.`__SCHEMA__`.`contract_monthly_metrics` (
  metrics_row_id           STRING NOT NULL,
  period_date              DATE NOT NULL,
  overall_sla_compliance   DOUBLE NOT NULL COMMENT 'Percentage 0–100',
  next_audit_date          DATE NOT NULL,
  open_deliverables_count  INT,
  breaches_mtd_count       INT
)
USING DELTA
COMMENT 'Contract-level monthly rollup for dashboards';

-- DDL_SPLIT
CREATE TABLE IF NOT EXISTS `__CATALOG__`.`__SCHEMA__`.`leader_profiles` (
  profile_id     STRING NOT NULL,
  persona_id     STRING NOT NULL,
  use_case_id    STRING NOT NULL,
  question_text  STRING NOT NULL,
  category       STRING,
  ask_count      INT NOT NULL,
  last_asked_ts  TIMESTAMP,
  source         STRING NOT NULL COMMENT 'seed | user',
  created_ts     TIMESTAMP NOT NULL
)
USING DELTA
PARTITIONED BY (persona_id)
COMMENT 'Leader prompt learning — weighted suggestions per persona';

-- DDL_SPLIT
CREATE TABLE IF NOT EXISTS `__CATALOG__`.`__SCHEMA__`.`action_rules` (
  rule_id           STRING NOT NULL,
  use_case_id       STRING NOT NULL,
  trigger_metric    STRING NOT NULL COMMENT 'sla_compliance_pct | obligation_status | supplier_overall_score | sla_breaches_count | days_to_next_audit',
  trigger_condition STRING NOT NULL COMMENT 'e.g. "< 90", "= Breached", ">= 3"',
  urgency           STRING NOT NULL COMMENT 'Immediate | This Week | Monitor',
  action_text       STRING NOT NULL,
  owner_role        STRING NOT NULL,
  contract_ref      STRING,
  active            BOOLEAN NOT NULL,
  created_ts        TIMESTAMP NOT NULL
)
USING DELTA
COMMENT 'Configurable threshold rules for Next Best Action generation (Phase 6)';
