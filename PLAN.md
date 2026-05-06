# Adaptive Leader Intelligence — Capita/TfL Demo Plan

## Context

**Why:** Adam Searle (CTO, Capita) demo on Thursday May 7. Capita manages the TfL contract and currently uses Power BI for contract performance reporting. The goal is to show how Databricks can replace that reporting layer with an adaptive AI experience — one that pre-populates prompts based on what the leader habitually asks, not generic FAQs.

**What:** A new standalone Databricks App in `/Users/sadiq.satwilkar/Documents/Git/capita_tfl_analytics/`. Code patterns copied and adapted from `agent_bricks_demo` — that project is left untouched. Config-driven so future use cases are a single new config file, no shared code changes.

**Stack:** **React** SPA for the UI (visual design and component structure will follow reference files you provide — not Gradio). **Python** backend (e.g. FastAPI) exposing REST APIs for chat, KPIs, leader profile, NBA, and static serving of the built frontend in production.

**Provisioning:** Create **all** Databricks-side resources via **APIs and automation** — Genie space, Knowledge Assistant / Vector Search wiring, Agent Bricks / model serving endpoint for the supervisor, UC volumes — with scripts that persist returned IDs into config or a generated `runtime_resources.json` checked in or produced at deploy time. Avoid one-off manual UI steps except where a platform API is unavailable (document any fallback).

**Workspace:** `ss_kibbim_azure_stable` (Azure)
**Deadline:** Thursday May 7, 2026
**Source of reuse:** `/Users/sadiq.satwilkar/Documents/Git/general/agent_bricks_demo/`

---

## Phase 1 — Project Scaffold + Config Layer

### What gets built
- Full directory structure with all `__init__.py` package markers
- `use_cases/base_config.py` — typed `UseCaseConfig` + `KPIDefinition` dataclasses
- `use_cases/capita_tfl/config.py` — all Capita/TfL values (persona, KPIs, sample questions, UC references)
- `config.py` — workspace globals + `USE_CASE` env var loader
- `requirements.txt` — all Python dependencies
- `databricks.yml` — app deployment config with `USE_CASE=capita_tfl` env var
- Minimal **`frontend/`** scaffold (package.json + placeholder) until Phase 5; React structure finalized when design reference files are added

### Files created
```
capita_tfl_analytics/
├── config.py
├── requirements.txt
├── databricks.yml
├── use_cases/
│   ├── __init__.py
│   ├── base_config.py
│   └── capita_tfl/
│       ├── __init__.py
│       └── config.py
└── frontend/                    ← scaffold only in Phase 1; UI built out in Phase 5
    └── (React app — structure TBD when design reference is added)
```

### Unit tests (automated)
- `python -c "from use_cases.base_config import UseCaseConfig, KPIDefinition; print('OK')"` — imports clean
- `python -c "from config import UC_CONFIG; print(UC_CONFIG.persona_name)"` — prints "Adam Searle"
- `USE_CASE=unknown python -c "from config import UC_CONFIG"` — raises `ValueError: Unknown USE_CASE`
- `python -c "from config import UC_CONFIG; assert len(UC_CONFIG.kpis) == 6; print('6 KPIs OK')"` — passes
- `python -c "from config import UC_CONFIG; assert len(UC_CONFIG.sample_questions) == 10; print('10 questions OK')"` — passes

### Acceptance criteria (you verify before authorising Phase 2)
- [ ] `python -c "from config import UC_CONFIG; print(UC_CONFIG)"` runs without errors and shows the correct persona name, title, and use_case_id
- [ ] All 6 KPIs have non-empty label, unit, icon, and sql_query fields
- [ ] All 10 sample questions have question, category, and weight fields

---

## Phase 2 — Synthetic Data + Unity Catalog Setup

### What gets built
- `sample_data/create_tfl_tables.sql` — 4 Delta table CREATE statements
- `sample_data/seed_tfl_data.py` — generates realistic synthetic data
- `scripts/setup_uc.py` — creates UC schema, runs DDL, seeds all 4 tables

### Tables created in `ss_kibbim_azure_stable.capita_tfl_demo`

| Table | Rows | Key demo data |
|---|---|---|
| `contract_deliverables` | ~200 | 60% Complete, 20% Open, 10% At Risk, 5% Breached |
| `sla_performance` | ~480 | 20 KPIs × 24 months, ~85% compliant, ~72 breaches |
| `supplier_performance` | ~120 | 5 suppliers × 24 months, 2 consistently Amber |
| `contract_monthly_metrics` | 24 | Compliance drops 93% → 88% in months 19–22 |

### Files created
```
capita_tfl_analytics/
├── sample_data/
│   ├── create_tfl_tables.sql
│   └── seed_tfl_data.py
└── scripts/
    └── setup_uc.py
```

### Unit tests (automated)
Run `python scripts/setup_uc.py --dry-run` to validate SQL without executing:
- All 4 CREATE TABLE statements parse without errors
- Seed data generator produces correct row counts before upload
- `python -c "from sample_data.seed_tfl_data import validate_data; validate_data()"` — asserts row counts, no nulls in key columns, date ranges correct

### Acceptance criteria (you verify before authorising Phase 3)
- [ ] UC Explorer at `ss_kibbim_azure_stable.capita_tfl_demo` shows all 4 tables
- [ ] `contract_deliverables` — run `SELECT status, COUNT(*) FROM contract_deliverables GROUP BY status` → shows mix of Open/At Risk/Breached/Complete
- [ ] `sla_performance` — run `SELECT COUNT(*) FROM sla_performance WHERE is_breach = true` → returns ~72
- [ ] `supplier_performance` — run `SELECT supplier_name, AVG(overall_score) FROM supplier_performance GROUP BY supplier_name` → 2 suppliers score below 70
- [ ] `contract_monthly_metrics` — run `SELECT period_date, overall_sla_compliance FROM contract_monthly_metrics ORDER BY period_date DESC LIMIT 6` → shows the compliance dip

---

## Phase 3 — Leader Profile Agent + Genie Space

### What gets built
- `sample_data/create_tfl_tables.sql` updated with `leader_profiles` table DDL
- `agents/leader_profile_agent.py` — reads/writes leader_profiles, computes time-decayed weights, seeds on first run, falls back to config if UC unavailable
- `scripts/seed_leader_profile.py` — pre-loads Adam Searle's 10 questions with synthetic ask history
- `scripts/create_genie_space.py` — **creates the Genie space via Databricks APIs** (space + instructions + example queries + table attachments as supported), writes `genie_space_id` into config or `runtime_resources.json`
- `docs/genie_instructions/` — source text for API payloads (instructions, joins, example SQL) — same content whether pasted or sent via API

### Leader profile table
```sql
CREATE TABLE leader_profiles (
    profile_id     STRING NOT NULL,
    persona_id     STRING NOT NULL,      -- "adam_searle_cto"
    use_case_id    STRING NOT NULL,
    question_text  STRING NOT NULL,
    category       STRING,
    ask_count      INT DEFAULT 0,
    last_asked_ts  TIMESTAMP,
    source         STRING DEFAULT 'user', -- "seed" | "user"
    created_ts     TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
) USING DELTA PARTITIONED BY (persona_id);
```

**Weight formula (Python, not stored):** `weight = ask_count × (0.95 ^ days_since_last_asked)`

### Genie Space setup (automated via script)
- Run `python scripts/create_genie_space.py` (with workspace auth) after Phase 2 tables exist
- Script attaches the 4 `capita_tfl_demo` tables, uploads/applies instructions from `docs/genie_instructions/`, registers the 8 example SQL queries, and persists the returned **Genie space ID** for the app config
- Validate in the Databricks UI only if needed for demo rehearsal — not the source of truth for creation

### Files created
```
capita_tfl_analytics/
├── agents/
│   ├── __init__.py
│   └── leader_profile_agent.py
├── scripts/
│   ├── seed_leader_profile.py
│   └── create_genie_space.py
└── docs/
    └── genie_instructions/
        ├── 01_text_instructions.md
        ├── 02_joins.md
        └── 03_example_queries.md
```

### Unit tests (automated)
- `python -c "from agents.leader_profile_agent import LeaderProfileAgent; print('import OK')"` — imports clean
- `python scripts/seed_leader_profile.py --dry-run` — prints questions that would be seeded, no DB writes
- `python -c "from agents.leader_profile_agent import LeaderProfileAgent; from config import UC_CONFIG; a = LeaderProfileAgent(UC_CONFIG); q = a.get_top_questions(5); assert len(q) == 5; print(q)"` — returns 5 questions
- `python -c "... a.log_question('test question'); ..."` — runs without error, verify row appears in UC Explorer

### Acceptance criteria (you verify before authorising Phase 4)
- [ ] `leader_profiles` table visible in UC Explorer with 10 pre-seeded rows for `adam_searle_cto`
- [ ] `SELECT question_text, ask_count FROM leader_profiles WHERE persona_id='adam_searle_cto' ORDER BY ask_count DESC LIMIT 5` → returns top 5 correctly weighted questions
- [ ] Genie space is live in Databricks UI — test these 3 questions directly in the Genie UI:
  - "Are we hitting our SLAs this month?" → returns a % figure
  - "Which obligations are at risk?" → returns a list with due dates
  - "How does SLA compliance compare this month vs last month?" → returns a comparison

---

## Phase 4 — Agents (Supervisor + Genie + RAG)

### What gets built
- `scripts/generate_pdfs.py` — generates 4 synthetic Capita/TfL contract PDFs
- `scripts/setup_knowledge_assistant.py` — **API-driven**: UC volume upload, Vector Search index + Knowledge Assistant creation/update, writes assistant / index IDs to config or `runtime_resources.json`
- `scripts/setup_supervisor_serving.py` (or equivalent) — **creates** the model serving / Agent Bricks endpoint for the supervisor (no hand-pasted URL); records endpoint name/URL for `uc_config`
- `agents/genie_agent.py` — adapted from `agent_bricks_demo`, takes `genie_space_id` from `uc_config`
- `agents/rag_agent.py` — adapted from `agent_bricks_demo`, takes `assistant_id` from `uc_config`
- `agents/supervisor.py` — adapted from `agent_bricks_demo`, builds system prompt from `uc_config` persona/domain
- Update use-case config with **`supervisor_endpoint`**, **`knowledge_assistant_id`**, vector index refs — all populated by setup scripts after resources exist

### Supervisor routing logic
- Route to **RAG agent** for: contract clauses, obligations, governance, "what does the contract say about..."
- Route to **Genie agent** for: metrics, trends, counts, comparisons, supplier scores, breach data
- Persona: addresses Adam Searle as CTO, flags risks proactively, concise data-led responses

### PDF knowledge base content (4 documents)
1. `contract_overview.pdf` — contract structure, parties, scope, term, value
2. `sla_framework.pdf` — SLA definitions, measurement methodology, 20 KPI descriptions, targets
3. `supplier_obligations.pdf` — subcontractor management, escalation procedures, penalty clauses
4. `governance_compliance.pdf` — reporting cadence, change control, audit requirements

### Files created
```
capita_tfl_analytics/
├── agents/
│   ├── genie_agent.py
│   ├── rag_agent.py
│   └── supervisor.py
├── use_cases/capita_tfl/
│   └── knowledge_base/
│       ├── contract_overview.pdf
│       ├── sla_framework.pdf
│       ├── supplier_obligations.pdf
│       └── governance_compliance.pdf
└── scripts/
    ├── generate_pdfs.py
    ├── setup_knowledge_assistant.py
    └── setup_supervisor_serving.py   ← creates supervisor / Agent Bricks endpoint via API
```

### Unit tests (automated)
- `python -c "from agents.genie_agent import GenieAgent; from config import UC_CONFIG; a = GenieAgent(UC_CONFIG); print('OK')"` — imports clean
- `python -c "from agents.supervisor import build_supervisor_instructions; from config import UC_CONFIG; s = build_supervisor_instructions(UC_CONFIG); assert 'Adam Searle' in s; print('persona injected OK')"` — persona in system prompt
- `python -c "from agents.rag_agent import RAGAgent; from config import UC_CONFIG; a = RAGAgent(UC_CONFIG); print('OK')"` — imports clean
- Test routing: `python scripts/test_routing.py` — sends 3 questions, asserts Genie handles metric questions and RAG handles contract questions

### Acceptance criteria (you verify before authorising Phase 5)
- [ ] Ask Genie agent directly: "What are the top 3 SLA breaches this month?" → returns data with chart
- [ ] Ask RAG agent directly: "What does the contract say about penalty clauses?" → returns answer citing a PDF document
- [ ] Ask Supervisor: "Are we hitting our SLAs?" → routes to Genie, returns compliance %
- [ ] Ask Supervisor: "What are our reporting obligations?" → routes to RAG, cites contract docs
- [ ] Supervisor response addresses "Adam" or refers to CTO-level context (not generic)

---

## Phase 5 — UI Layer (Full App)

### What gets built
- **`frontend/`** — React application (routing, chat view, dashboard view). Implementation follows **your shared React reference files** for layout, typography, and interaction patterns.
- **`api/`** (or top-level `main.py`) — Python ASGI app (e.g. FastAPI): REST endpoints for chat, KPI queries, leader-profile chips, session/conversation handling; serves the production SPA bundle.
- Backend wires `UC_CONFIG`, `LeaderProfileAgent`, and agent stack; logs user questions to `leader_profiles` asynchronously after each send.

### Local dev
- Backend: `uvicorn` (or framework equivalent) on a chosen port (e.g. `8000`)
- Frontend: Vite/webpack dev server with **proxy** to the API for same-origin API calls during development
- Production (Databricks App): single process serves API + static files from `frontend/dist`

### Suggestion chip UX — mirroring Genie's pattern

Suggestions are surfaced **inline within the chat flow**, not as a separate panel. This matches how Genie presents follow-up questions.

**On conversation start** — Five suggestion chips loaded from `GET /api/suggestions` (backed by `leader_profile_agent.get_top_questions(5)`). Render as clickable chips below the input:

```
┌─────────────────────────────────────────────────────────────┐
│  Good morning, Adam. How can I help you today?              │
│                                                             │
│  ┌──────────────────────────────────┐                       │
│  │ Are we hitting our SLAs?         │  ← clickable chip    │
│  └──────────────────────────────────┘                       │
│  ┌─────────────────────────────────────────┐                │
│  │ Which obligations are at risk?          │                │
│  └─────────────────────────────────────────┘                │
│  ┌────────────────────────────────────────────────┐         │
│  │ How does performance compare to last period?   │         │
│  └────────────────────────────────────────────────┘         │
│  ... (2 more)                                               │
│                                                             │
│  [  Ask anything about the TfL contract...           ] [→] │
└─────────────────────────────────────────────────────────────┘
```

**After each AI response** — 2–3 contextual follow-up suggestions returned in the API payload (`suggested_followups`) and rendered as chips below the assistant message, exactly as Genie does:

```
  Assistant: Overall SLA compliance this month is 88.2%, down from
  93.1% last month...

  ╭──────────────────────────────────────────╮
  │ Suggested follow-ups:                    │
  │ [What drove the drop?]                   │
  │ [Which SLAs specifically breached?]      │
  │ [Show me the trend over 6 months]        │
  ╰──────────────────────────────────────────╯
```

**Implementation approach:**
- Start-of-conversation chips: React `useEffect` on chat mount calls suggestions API; optional refresh after profile updates.
- Post-response chips: chat completion endpoint returns JSON `{ answer, suggested_followups[], ... }`; React renders chips under the assistant message.
- Clicking any chip (start or follow-up) submits that question via the same chat API — same behaviour as Genie.
- After each submitted question: `leader_profile_agent.log_question(message)` runs in a **background task** so it never blocks the HTTP response.

### Files created (indicative)
```
capita_tfl_analytics/
├── main.py                      ← ASGI entrypoint (or api/main.py)
├── api/
│   ├── __init__.py
│   └── routes/                  ← chat, kpi, suggestions, health
├── frontend/
│   ├── package.json
│   ├── vite.config.ts           ← dev proxy to Python API
│   └── src/
│       ├── App.tsx
│       ├── pages/Chat.tsx
│       └── pages/Dashboard.tsx
└── (design tokens / components per your reference files)
```

### Unit tests (automated)
- `python -c "from api.routes import ..."` / FastAPI `TestClient` — health + `/api/suggestions` returns 5 items with expected shape
- `npm run build` (in `frontend/`) — production bundle builds without errors
- `python -c "from agents.leader_profile_agent import LeaderProfileAgent; from config import UC_CONFIG; a = LeaderProfileAgent(UC_CONFIG); ex = a.get_top_questions(5); assert all('question' in q for q in ex); print('chips OK')"` — backend still returns correct chip payload shape
- Manual or Playwright (optional): open `http://localhost:<vite-port>` proxied to API — chat and dashboard load

### Acceptance criteria — full 4-act demo run-through (you verify before authorising Phase 6)
- [ ] **Act 1:** App loads → greeting visible → 5 suggestion chips appear below the input box (Genie-style)
- [ ] **Act 1:** Click "Are we hitting our SLAs this month?" chip → question submits directly → Genie returns SLA compliance % with chart
- [ ] **Act 2:** Click "Which obligations are currently at risk?" → returns prioritised list with due dates
- [ ] **Act 2:** Type "What is the penalty exposure on those obligations?" → Genie returns £ value
- [ ] **Act 3:** Click "How does this period compare to last?" → shows the compliance dip (93% → 88%)
- [ ] **Act 3:** Dashboard tab → all 6 KPI cards show data (not zeros or errors)
- [ ] **Act 3:** Type "Why did we drop in the last 3 months?" → RAG agent responds citing contract docs
- [ ] **Act 4:** Type a new question not in the list → ask it → check `leader_profiles` table → row added
- [ ] **Act 4:** Reload app → new question appears in the top 5 suggestions

---

## Phase 6 — Next Best Action (NBA)

The NBA feature transforms the app from insight delivery to decision support. The **dashboard** always shows **Priority Actions** (data-driven). In **chat**, NBA is **on demand** (button or natural-language intent) so routine Q&A stays fast and uncluttered. Each NBA item is 1–3 grounded recommendations citing a contract clause and/or a data threshold.

**Databricks components used:**
- **Unity Catalog** — `action_rules` Delta table stores configurable thresholds
- **Vector Search** — retrieves relevant contract clauses (reuses existing RAG index)
- **Foundation Model APIs** — generates structured NBA output
- **Agent Bricks** — NBA generator wired as a fourth tool in the supervisor

---

### Phase 6a — Action Rules Data Layer

#### What gets built
- `action_rules` Delta table in `ss_kibbim_azure_stable.capita_tfl_demo`
- Seeded with Capita/TfL specific rules covering SLA breaches, obligation risk, supplier performance
- `agents/action_rules_agent.py` — queries the table to find rules matching the current data context

#### Action rules table schema
```sql
CREATE TABLE action_rules (
    rule_id          STRING NOT NULL,
    use_case_id      STRING NOT NULL,       -- "capita_tfl"
    trigger_metric   STRING,                -- "sla_compliance_pct", "supplier_score", etc.
    trigger_condition STRING,               -- "< 90", "= Breached", ">= 3 consecutive months"
    urgency          STRING,                -- "Immediate" | "This Week" | "Monitor"
    action_text      STRING,                -- "Initiate formal remediation plan..."
    owner_role       STRING,                -- "Contract Manager", "CTO", "Service Desk Lead"
    contract_ref     STRING,                -- "Clause 8.3", "Schedule 2, Section 4"
    active           BOOLEAN DEFAULT TRUE
) USING DELTA;
```

#### Seed rules (examples)
| Trigger | Condition | Urgency | Action |
|---|---|---|---|
| `sla_compliance_pct` | < 90% | Immediate | Initiate remediation plan — clause 8.3 requires submission within 5 working days |
| `sla_compliance_pct` | < 95% but ≥ 90% | This Week | Review SLA performance with service leads — approaching breach threshold |
| `obligation_status` | = Breached | Immediate | Raise formal breach notice to TfL contract manager within 48 hours |
| `obligation_status` | = At Risk | This Week | Escalate to TfL contract manager — schedule remediation review |
| `supplier_overall_score` | < 70 for 3+ months | Immediate | Trigger Performance Improvement Plan — Amber threshold exceeded |
| `supplier_overall_score` | < 80 | This Week | Request root cause analysis from supplier — submit by end of week |
| `sla_breaches_count` | ≥ 5 in month | Immediate | Convene emergency contract review — penalty exposure exceeds threshold |

#### Files created
```
capita_tfl_analytics/
├── agents/
│   └── action_rules_agent.py
└── sample_data/
    └── seed_action_rules.py
```

#### Unit tests (automated)
- `python -c "from agents.action_rules_agent import ActionRulesAgent; print('import OK')"` — imports clean
- `python -c "from agents.action_rules_agent import ActionRulesAgent; from config import UC_CONFIG; a = ActionRulesAgent(UC_CONFIG); rules = a.get_matching_rules({'sla_compliance_pct': 87}); assert len(rules) > 0; print(rules)"` — returns matching rules
- `python -c "... rules = a.get_matching_rules({'sla_compliance_pct': 97}); assert all(r['urgency'] == 'Monitor' for r in rules); print('threshold OK')"` — no Immediate/This Week rules triggered at 97%

#### Acceptance criteria (authorise Phase 6b)
- [ ] `action_rules` table visible in UC Explorer with all seed rules loaded
- [ ] `SELECT * FROM action_rules WHERE trigger_metric = 'sla_compliance_pct' ORDER BY urgency` → returns tiered rules correctly
- [ ] `ActionRulesAgent.get_matching_rules({'sla_compliance_pct': 87})` → returns at least one "Immediate" rule
- [ ] `ActionRulesAgent.get_matching_rules({'sla_compliance_pct': 99})` → returns only "Monitor" rules or empty

---

### Phase 6b — NBA Generation Agent

#### What gets built
- `agents/nba_agent.py` — the NBA generator
  - Takes: answer text + matched action rules + contract clauses from Vector Search
  - Returns: structured list `[{action, urgency, rationale, owner_role, contract_ref}]`
  - Uses **Foundation Model APIs** for generation (structured output / JSON mode)
  - Uses existing Vector Search index to retrieve relevant contract clauses
- `scripts/test_nba_agent.py` — standalone test script

#### How it works
```
answer_text + data_context
        ↓
ActionRulesAgent.get_matching_rules()   → matched threshold rules
        ↓
VectorSearch.similarity_search()        → top 3 relevant contract clauses
        ↓
Foundation Model API                    → structured NBA output (JSON)
        ↓
[{action, urgency, rationale, owner_role, contract_ref}]
```

#### Foundation Model API prompt structure
System prompt instructs the model to:
- Generate exactly 1–3 actions (never more)
- Assign one urgency level per action: Immediate / This Week / Monitor
- Ground every action in either a matched rule or a retrieved contract clause
- Never invent contract references — only cite what Vector Search returned
- Output valid JSON matching the NBA schema

#### Files created
```
capita_tfl_analytics/
├── agents/
│   └── nba_agent.py
└── scripts/
    └── test_nba_agent.py
```

#### Unit tests (automated)
- `python -c "from agents.nba_agent import NBAAgent; print('import OK')"` — imports clean
- `python scripts/test_nba_agent.py --scenario sla_breach` — given a mock SLA breach answer, returns valid NBA JSON with ≥ 1 Immediate action
- `python scripts/test_nba_agent.py --scenario all_green` — given a healthy answer, returns only Monitor actions
- `python scripts/test_nba_agent.py --validate-schema` — asserts all returned objects have action, urgency, rationale, owner_role, contract_ref fields
- `python scripts/test_nba_agent.py --no-hallucination` — asserts contract_ref values only contain text found in the retrieved clauses

#### Acceptance criteria (authorise Phase 6c)
- [ ] Given answer: *"SLA compliance is 87.2% this month, down from 93.1%"* → NBA returns at least 1 Immediate action citing the remediation clause
- [ ] Given answer: *"All SLAs compliant, no obligations at risk"* → NBA returns only Monitor-level actions (no false alarms)
- [ ] Every returned action has a non-empty `contract_ref` or `rationale` field — no naked recommendations
- [ ] NBA generation completes in under 5 seconds (acceptable for demo)

---

### Phase 6c — Supervisor Integration

#### Design choice (6c vs 6d aligned)
- **Do not** run full NBA generation automatically after **every** Genie/RAG turn — that would add latency (keep typical Q&A under ~10 seconds for the supervisor path) and duplicates what the dashboard already shows.
- **Do** register `generate_next_best_actions` as a **fourth tool** and invoke it when:
  - The user’s message matches **NBA intent** (e.g. “what should I do”, “next steps”), **or**
  - The client calls a dedicated **`POST /api/nba`** (or equivalent) with **full conversation context** for the chat **“What should I do?”** button.
- Standard chat replies return `{ answer_text, suggested_followups }` **without** `next_best_actions` unless the turn is an NBA request.
- **Dashboard** Priority Actions use **`GET /api/priority-actions`** (or KPI + `ActionRulesAgent` + optional `NBAAgent` formatting) — **no chat transcript required**.

#### What gets built
- `generate_next_best_actions` registered as a fourth tool in `agents/supervisor.py`
- Supervisor routing: NBA intent → gather context → call NBA tool → return `{ answer_text?, next_best_actions, nba_surface: "modal" }` as appropriate
- Dedicated NBA endpoint for the toolbar button (same tool under the hood)
- `scripts/test_supervisor_nba.py` — tests NBA tool + NBA intent + priority-actions path

#### Supervisor flow (NBA request path)
```
User question (NBA intent OR POST /api/nba)
      ↓
Supervisor (or thin NBA handler) assembles answer context + data_context
      ↓
Calls generate_next_best_actions(answer, data_context, conversation)
      ↓
Returns { next_best_actions: [...] }  (+ optional answer_text if combined turn)
```

#### Standard Q&A flow (no automatic NBA)
```
User question (normal analytics / contract)
      ↓
Supervisor routes to Genie or RAG
      ↓
Returns { answer_text, suggested_followups }   ← no next_best_actions
```

#### Files modified
```
capita_tfl_analytics/
└── agents/
    └── supervisor.py    ← add NBA tool, update system prompt, update return schema
```

#### Unit tests (automated)
- `python scripts/test_supervisor_nba.py` — NBA intent or `/api/nba` returns `next_best_actions`; normal question returns **no** `next_best_actions`
- `python scripts/test_supervisor_nba.py --check-urgency` — at least one Immediate action when context reflects at-risk seed data
- `python scripts/test_supervisor_nba.py --check-no-duplication` — NBA actions are not mere repetition of the answer text
- `python scripts/test_supervisor_nba.py --priority-actions` — `GET /api/priority-actions` returns grouped actions for dashboard

#### Acceptance criteria (authorise Phase 6d)
- [ ] Ask supervisor "Which obligations are at risk?" (normal) → `answer_text` present; **`next_best_actions` omitted or empty**
- [ ] Ask "What should I do about the SLA breach?" or call **`POST /api/nba`** → `next_best_actions` populated with urgency
- [ ] Ask supervisor "Are all SLAs compliant?" (healthy data) in NBA mode → Monitor-only actions, no false alarms
- [ ] NBA recommendations reference Adam Searle's role or Capita's context (not generic)
- [ ] Typical Q&A round-trip stays snappy; **NBA path** completes within ~10s including generation

---

### Phase 6d — NBA UI: Chat Popup + Dashboard Priority Actions Widget

NBA surfaces in two distinct places with different triggers and visual treatments.

#### What gets built
- **`frontend/src/components/NBAModal.tsx`** (name flexible) — modal for on-demand NBA (toolbar + NL intent)
- **`frontend/src/components/PriorityActions.tsx`** — dashboard widget (summary badges, list, refresh)
- **Shared types** — `NextBestAction` in TypeScript, mirrored by Pydantic models in Python
- **`frontend/src/api/client.ts`** — `fetch` wrappers for `/api/nba`, `/api/priority-actions`
- Chat page — "What should I do?" button + NL intent routing (calls NBA endpoint, opens modal)
- Dashboard page — Priority Actions widget **above** KPI cards

---

#### Surface 1: Chat — On-Demand NBA Popup

NBA in the chat view is **never automatic**. It appears only when Adam explicitly requests it:

**Trigger A — Button:** A `⚡ What should I do?` button sits in the chat toolbar. Clicking it **`POST`s full conversation history** to `/api/nba` and renders the result in a **React modal** overlay.

**Trigger B — Natural language:** If Adam types anything matching intent patterns (`what should I do`, `what are my next steps`, `what action should I take`, `how should I respond to this`) the backend recognises NBA intent, runs the same NBA pipeline, and the client opens the modal with the returned actions (optional: a minimal assistant line like “Here are recommended actions” — **no** long duplicate of the full NBA list in the chat stream).

```
┌─────────────────────────────────────────────────────────────┐
│  [Chat history...]                                          │
│                                                             │
│  Assistant: SLA compliance is 87.2%, down from 93.1%...    │
│                                                             │
│  [Ask anything...                              ] [→]        │
│  [⚡ What should I do?]                                     │  ← toolbar button
└─────────────────────────────────────────────────────────────┘

           ┌──────────────────────────────────────────┐
           │  ⚡ Priority Actions                  [×] │  ← modal popup
           │  Based on your conversation context       │
           │  ────────────────────────────────────     │
           │  🔴 Immediate                             │
           │  Initiate remediation plan for OBL-042    │
           │  Clause 8.3 — due within 5 working days  │
           │  Owner: Contract Manager                  │
           │                                           │
           │  🟡 This Week                             │
           │  Schedule supplier review with Atos       │
           │  PIP threshold exceeded (3 months Amber)  │
           │  Owner: Adam Searle                       │
           │                                           │
           │  🟢 Monitor                               │
           │  Track SLA-007 weekly — at 94.1% vs 95%  │
           └──────────────────────────────────────────┘
```

- Popup closes on `[×]` or click-outside
- NBA is generated from the **full conversation context**, not just the last message — so it reflects everything discussed in the session
- If conversation is empty (no messages yet), button is disabled with tooltip: *"Ask a question first to generate actions"*

---

#### Surface 2: Dashboard — Priority Actions Widget

The dashboard tab has a **Priority Actions widget** that is always visible, front-and-centre — the first thing Adam sees when he opens the dashboard tab.

```
┌──────────────────────────────────────────────────────────────────────┐
│  ⚡ Priority Actions                                    [↻ Refresh]  │
│  Based on current contract data                                      │
│  ─────────────────────────────────────────────────────────────────   │
│  🔴 Immediate (2)          🟡 This Week (3)         🟢 Monitor (1)  │
│                                                                      │
│  🔴 Initiate remediation plan — SLA compliance at 87.2%             │
│     Clause 8.3 · Owner: Contract Manager                            │
│                                                                      │
│  🔴 Raise breach notice for OBL-042 · Due: 3 days                   │
│     Clause 12.1 · Owner: Contract Manager                           │
│                                                                      │
│  🟡 Schedule supplier review with Atos · Score: 62/100              │
│     PIP threshold exceeded · Owner: Adam Searle                     │
│  ... (2 more This Week)                           [Show all]        │
└──────────────────────────────────────────────────────────────────────┘

  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
  │  Overall    │  │ Obligations │  │  Avg SLA    │  │    Open     │
  │ SLA Compl. │  │  At Risk    │  │ Score vs T. │  │Deliverables │
  │   87.2%    │  │      4      │  │   91.4%    │  │     23      │
  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘
```

- Widget loads on dashboard open, evaluating live KPI values against `action_rules` table
- **No conversation needed** — purely data-driven via `ActionRulesAgent`
- Summary badge row shows counts by urgency at a glance (🔴 2 · 🟡 3 · 🟢 1)
- Shows top 4 actions inline; `[Show all]` expands the full list
- `[↻ Refresh]` re-queries live data
- KPI metric cards sit **below** the Priority Actions widget — actions first, numbers second

#### Files created/modified
```
capita_tfl_analytics/
├── api/routes/nba.py         ← POST /api/nba, GET /api/priority-actions
└── frontend/src/
    ├── components/NBAModal.tsx
    ├── components/PriorityActions.tsx
    ├── pages/Chat.tsx        ← toolbar + modal wiring
    └── pages/Dashboard.tsx   ← widget at top
```

#### Unit tests (automated)
- FastAPI `TestClient`: `/api/nba` with mock conversation returns structured JSON; empty conversation returns 400 or `{ actions: [] }` per contract
- `GET /api/priority-actions` returns badge counts consistent with seed data
- `npm test` or component tests (optional) — modal renders with mocked payload

#### Acceptance criteria (authorise Phase 7 — Deployment)
**Chat popup:**
- [ ] "What should I do?" button is visible in the chat toolbar
- [ ] Clicking button with no conversation history → button disabled or shows "Ask a question first"
- [ ] Clicking button after asking "Which obligations are at risk?" → modal opens with ≥1 Immediate action
- [ ] Typing "what should I do next?" in chat → modal opens (intent detection works)
- [ ] Modal closes on [×] click
- [ ] NBA actions cite contract clauses or data thresholds — no uncited recommendations

**Dashboard Priority Actions widget:**
- [ ] Widget is the first visible element on the dashboard tab (above KPI cards)
- [ ] Widget loads with actions on page open — no manual trigger needed
- [ ] Summary badges show correct counts (🔴 2 · 🟡 3 · 🟢 1) matching the seed data scenario
- [ ] 🔴 Immediate actions are listed before 🟡 This Week and 🟢 Monitor
- [ ] `[↻ Refresh]` re-queries and updates the widget
- [ ] Widget renders correctly when no Immediate actions exist (shows "No immediate actions — monitoring only")

---

## Phase 7 — Databricks App Deployment

### What gets built
- `databricks.yml` updated with correct app name, `USE_CASE` env var, target workspace, **build step** that runs `npm ci && npm run build` in `frontend/` before packaging (or equivalent)
- App deployed to `ss_kibbim_azure_stable` via `databricks bundle deploy`
- Full demo run-through on deployed URL (not localhost)

### Unit tests (automated)
- `databricks bundle validate` — no errors in `databricks.yml`
- `curl https://<deployed-url>/` → HTTP 200
- `python scripts/smoke_test_deployed.py` — hits the deployed app URL and verifies response

### Acceptance criteria (final sign-off)
- [ ] Deployed app URL opens in browser → correct persona header visible
- [ ] Full 4-act demo works on deployed app (not localhost)
- [ ] KPI dashboard refreshes with live data
- [ ] Question learning loop works on deployed app (log question → reload → appears in suggestions)
- [ ] App accessible to a second person (share URL and verify they can use it)

---

## Summary: Phase Gate Overview

| Phase | Builds | Key acceptance test |
|---|---|---|
| 1 — Config Layer | Project scaffold, use-case config | `python -c "from config import UC_CONFIG; print(UC_CONFIG.persona_name)"` → "Adam Searle" |
| 2 — Synthetic Data | 4 Delta tables in UC | UC Explorer shows tables with correct row counts and data distribution |
| 3 — Leader Profile + Genie | `leader_profiles` table, Genie space live | Genie answers 3 test questions directly in Databricks UI |
| 4 — Agents | Supervisor, Genie agent, RAG agent | Supervisor routes correctly; responses reference Adam Searle persona |
| 5 — UI | React + FastAPI locally | All 4 demo acts pass on localhost |
| 6a — NBA: Action Rules | `action_rules` Delta table + agent | Threshold rules correctly trigger at right values |
| 6b — NBA: Generation Agent | `nba_agent.py` using FMApi + Vector Search | Given SLA breach answer → returns ≥1 Immediate action with contract ref |
| 6c — NBA: Supervisor Integration | NBA tool + `/api/nba` + `/api/priority-actions` | Normal Q&A has no automatic NBA; NBA path returns actions; dashboard priority actions load |
| 6d — NBA: UI | React modal + Priority Actions widget | Chat on-demand NBA; dashboard data-driven; urgency styling + empty states |
| 7 — Deployment | Live Databricks App | Full demo including NBA works on deployed URL |
