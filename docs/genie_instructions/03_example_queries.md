# Example SQL (mirrors API payload)

Eight benchmark queries ship in **`genie_space_payload.py`** (`_example_question_sqls`). They cover:

1. Latest overall SLA compliance %
2. At-risk obligations with due dates
3. This month vs last month compliance (last two monthly rows)
4. Breach count for the current calendar month
5. Suppliers with lifetime average score &lt; 70
6. Breaches by KPI (last 30 days)
7. Last six months of monthly compliance (trend)
8. Open deliverables due in the next 14 days

Use fully qualified names: `` `{catalog}`.`{schema}`.`table` `` matching your workspace.
