# Recommended joins (TfL demo)

Genie should prefer **single-table** answers when possible. Use joins only when the question spans entities.

## Deliverables ↔ supplier scores

- **Join key**: `contract_deliverables.supplier_name` = `supplier_performance.supplier_name`
- **Grain note**: Deliverables are obligation-level; supplier_performance is **monthly**. Filter supplier_performance to the relevant `period_date` (e.g. latest month) when comparing supplier score to a deliverable.

## SLA detail ↔ monthly rollup

- **Join key**: `DATE_TRUNC('month', sla_performance.period_date)` = `contract_monthly_metrics.period_date`
- Use when correlating KPI-level breaches with headline monthly compliance.

## Within-table aggregations

- **sla_performance**: Group by `kpi_name`, `period_date` for breach trends.
- **contract_monthly_metrics**: Order by `period_date` for compliance trajectory.
