# Build & Ship Pipeline — AI Agent Knowledge Base

> Machine-readable reference for AI coding assistants (Claude Code, Copilot, Cursor, etc.)
> When a human asks you to modify this project, read this file first.
>
> **Keep docs in sync:** when you change behaviour, update the docs it affects in the
> same commit/PR — this file and the relevant `agents/*.md`. Verify stated facts (test
> counts, budget ceilings, signatures) still match the code. A change that updates code
> but not its docs is incomplete. Full mapping: `agents/README.md` → "When you make a change".

---

## 0. Quick orientation

This is a **LangGraph multi-agent system** wrapped in a **FastAPI + React web UI**.
A user types a feature request; 12+ LLM agents collaborate to plan, code, test, review, and report it — all within a hard budget ceiling and with full audit logging.

The system has three distinct layers:
1. **Pipeline core** (`src/`) — LangGraph graph, agents, governance, DB schema
2. **Web UI backend** (`ui/backend/`) — FastAPI app serving the React SPA and REST+WebSocket API
3. **Web UI frontend** (`ui/frontend/src/`) — React + Vite + Tailwind, real-time streaming

---

## 1. Directory map

```
build-ship-pipeline/
├── config/
│   ├── budget.yaml          ← global cost/token/step ceilings + per-action hard caps
│   └── prices.yaml          ← USD/1K token prices + default model per agent
├── src/
│   ├── state.py             ← PipelineState TypedDict + initial_state() factory
│   ├── graph.py             ← StateGraph wiring (nodes + edges + conditional routers)
│   ├── config.py            ← Loads config/*.yaml into BUDGET_CFG, PRICES_CFG singletons
│   ├── agents/
│   │   ├── base.py          ← call_model(), inject_skills(), model_kwargs_from_state()
│   │   ├── dev/             ← planner, coder, docker, observability, tester, debugger, reviewer
│   │   └── review/          ← security, perf, style, coverage, supervisor
│   ├── governance/
│   │   ├── governed.py      ← governed() decorator: skill toggle + budget guard + tracing
│   │   ├── guard.py         ← budget_guard() + BudgetExceeded + estimate_cost()
│   │   └── dynamic.py       ← fair-share dynamic per-action cap calculation
│   ├── db/
│   │   ├── schema.sql       ← 12-table Postgres schema (run once)
│   │   └── repo.py          ← PipelineRepo (psycopg3 connection pool, role groups)
│   ├── rag/                 ← retrieval-augmented generation (see §13)
│   │   ├── base.py          ← Document, RetrievalResult, Retriever ABC
│   │   ├── chunker.py       ← Fixed / Sentence / Recursive chunkers
│   │   ├── bm25.py          ← in-memory Okapi BM25 + Postgres FTS BM25
│   │   ├── dense.py         ← litellm embeddings (in-memory cosine + pgvector)
│   │   ├── hybrid.py        ← Reciprocal Rank Fusion of any retrievers
│   │   ├── graph.py         ← entity-graph RAG (in-memory + Postgres)
│   │   ├── hyde.py          ← Hypothetical Document Embeddings
│   │   ├── multi_query.py   ← LLM query expansion + vote merge
│   │   ├── reranker.py      ← LLM cross-encoder reranker
│   │   ├── instrument.py    ← InstrumentedRetriever (OTel + input guards)
│   │   ├── guards.py        ← validate_query / validate_k / validate_corpus
│   │   ├── indexer.py       ← PipelineIndexer (plan/artifacts/knowledge/memory)
│   │   ├── recipes.py       ← 5 pipeline use cases (see §13)
│   │   └── __init__.py      ← create_retriever() factory + retrieve_for_agent()
│   ├── nodes/
│   │   ├── approval.py      ← approval_gate_node (asyncio.Event gating between plan+code)
│   │   ├── halt.py          ← halt_node (terminal — sets phase="halted")
│   │   └── report.py        ← report_node (terminal; persists run memory for RAG)
│   └── observability/
│       └── tracing.py       ← OpenTelemetry spans + Prometheus counters
├── ui/
│   ├── backend/
│   │   ├── app.py           ← FastAPI factory (CORS, rate limit, routers, SPA fallback)
│   │   ├── auth.py          ← bcrypt + HS256 JWT + httpOnly cookie + rate limiter
│   │   ├── dependencies.py  ← get_db() singleton + get_current_user() cookie validator
│   │   ├── models.py        ← Pydantic schemas for all API I/O
│   │   ├── runs.py          ← /api/runs endpoints + _compute_skill_context() + pipeline thread
│   │   ├── skills.py        ← /api/skills CRUD endpoints
│   │   ├── ws.py            ← WebSocket handler + thread-safe publish()
│   │   └── seed.py          ← python -m ui.backend.seed (users + system skills)
│   └── frontend/src/
│       ├── App.tsx           ← root: auth gate, layout, skill state, SkillsManager overlay
│       ├── types.ts          ← TypeScript interfaces (Skill, RunSummary, WSEvent, etc.)
│       ├── api/              ← fetch wrappers (auth.ts, runs.ts, skills.ts)
│       ├── components/
│       │   ├── Sidebar.tsx       ← run history list + skills manager trigger
│       │   ├── ChatWindow.tsx    ← feature input, model picker, SessionSkills, execute/stop
│       │   ├── StreamPanel.tsx   ← real-time step cards, budget bars, artifacts, findings
│       │   ├── SessionSkills.tsx ← per-run skill override picker (collapsible)
│       │   ├── SkillsManager.tsx ← global skill CRUD slide-over panel
│       │   ├── ApprovalGate.tsx  ← modal that gates human approval before coding
│       │   ├── ModelPicker.tsx   ← provider + model + endpoint dropdowns
│       │   └── Login.tsx         ← login form
│       └── hooks/
│           ├── useRun.ts     ← run state machine (idle→running→done/halted/stopped)
│           └── useWebSocket.ts ← connects to /ws/runs/{id}, feeds events to useRun
├── tests/unit/
│   ├── test_governance.py   ← 13 governance tests (no LLM calls)
│   └── test_state.py        ← 3 state initialisation tests
└── docker-compose.yml       ← postgres + OTel collector + Prometheus + Loki + Tempo + Grafana + UI + nginx
```

---

## 2. Agent graph topology

```
START
  │
  ▼
planner ──────────────────────────────────────────────────────────┐
  │                                                               │ (verdict=critical)
  ▼                                                               │
approval_gate                                                      │
  │ approved                                                       │
  ▼                                                               │
coder ◄─── debugger ◄──(test fail, attempts < max)               │
  │                                                               │
  ▼                                                               │
docker → observability → tester                                   │
                           │ passed=True                          │
                           ▼                                       │
                        reviewer                                   │
                           │                                       │
                           ▼                                       │
                     review_supervisor                             │
                           │                                       │
                     security → perf → style → coverage            │
                           │                                       │
                     review_verdict ──────────────────────────────┘
                           │ clean/minor
                           ▼
                        report → END
                           
Any node can return phase="halted" → routes to halt → END
```

**Key routing rules:**
- `approval_gate`: if `require_approval=False`, immediately returns `approval_status="approved"`
- `tester`: loops back to `debugger` up to `BUDGET_CFG.debug_max_attempts` times (default 3), then escalates to `planner`
- `review_verdict`: critical verdict sends everything back to `planner` for a full redo
- Any `BudgetExceeded` exception in a node returns `{"phase": "halted", "halt_reason": ...}`

---

## 3. PipelineState — fields and reducers

All state flows through `PipelineState` (a TypedDict in `src/state.py`).

| Field | Type | Reducer | Notes |
|-------|------|---------|-------|
| `run_id` | `str` | replace | UUID, set at run start |
| `feature_request` | `str` | replace | user input, immutable |
| `phase` | `Literal` | replace | `"dev"` → `"review"` → `"done"/"halted"` |
| `plan` | `dict` | replace | planner output |
| `tech_stack` | `list[str]` | replace | planner output |
| `artifacts` | `list[Artifact]` | **add** | accumulates across coder iterations |
| `test_results` | `dict` | replace | latest tester output |
| `debug_attempts` | `int` | replace | incremented by debugger |
| `findings` | `list[Finding]` | **add** | review agents append, never replace |
| `verdict` | `str\|None` | replace | set by review_verdict |
| `budget` | `Budget` | replace | updated by governed() after each call |
| `audit` | `list[dict]` | **add** | every node appends a record |
| `halt_reason` | `str\|None` | replace | set when phase→halted |
| `require_approval` | `bool` | replace | from StartRunRequest |
| `approval_status` | `str\|None` | replace | managed by approval_gate_node |
| `model_config` | `dict` | replace | {provider, model, api_base, api_key} |
| `skill_context` | `dict` | replace | {agent_name: combined_prompt_text} — set once at run start |
| `enabled_agents` | `list` | replace | agents minus disabled toggles — set once at run start |
| `_skill_ctx` | `str` | replace | **internal** — set by governed() per-node call, never in initial_state |

**INVARIANT:** Fields with `Annotated[list, add]` reducer (artifacts, findings, audit) must only be returned as new lists from agents — never return the full accumulation, just the new items. LangGraph merges them.

---

## 4. governed() decorator — what it does

Every agent node is wrapped with `governed(agent_name, db)(node_fn)`.

Execution order inside `governed()`:

1. **Skill toggle check** — if `agent_name not in state["enabled_agents"]`, return `{}` immediately (zero cost)
2. **Model resolution** — reads `state["model_config"]["model"]` or falls back to `PRICES_CFG.model_for(agent_name)`
3. **Skill context injection** — copies `state["skill_context"][agent_name]` into `state["_skill_ctx"]`
4. **OTel span** — wraps steps 5–9
5. **Pre-flight budget check** — calls `budget_guard()` which raises `BudgetExceeded` if limits would be exceeded
6. **Node call** — `result, usage = node_fn(state, model)` 
7. **Cost reconciliation** — actual cost written to `budget_ledger` via `db.reconcile_ledger()`
8. **Budget update** — new `Budget` dict merged into result
9. **Audit append** — step metadata appended to result's `audit` list

**Node function signature:**
```python
def my_node(state: PipelineState, model: str) -> tuple[dict, Usage]:
    ...
    return {"my_field": value}, Usage(in_=100, out=200)
```

---

## 5. How to add a new agent

1. **Create** `src/agents/dev/myagent.py` or `src/agents/review/myagent.py`:
   ```python
   from src.agents.base import Usage, call_model, inject_skills, model_kwargs_from_state
   from src.state import PipelineState

   _SYSTEM = "You are the MyAgent agent..."

   def myagent_node(state: PipelineState, model: str) -> tuple[dict, Usage]:
       user_msg = f"Input: {state['some_field']}"
       text, usage = call_model(
           model, inject_skills(_SYSTEM, state), user_msg,
           **model_kwargs_from_state(state)
       )
       return {"some_output_field": text}, usage
   ```

2. **Add to `_ALL_AGENTS`** in `src/state.py`:
   ```python
   _ALL_AGENTS = [..., "myagent"]
   ```

3. **Wire into graph** in `src/graph.py`:
   ```python
   from src.agents.dev.myagent import myagent_node
   g.add_node("myagent", governed("myagent", db)(myagent_node))
   g.add_edge("previous_node", "myagent")
   g.add_edge("myagent", "next_node")
   ```

4. **Add default model** in `config/prices.yaml`:
   ```yaml
   agent_models:
     myagent: claude-haiku-4-5-20251001
   expected_output_tokens:
     myagent: 1000
   ```

---

## 6. Skill system

Skills modify agent behaviour at run time without code changes.

### Two kinds:

**`prompt_injection`** — Appends text to agent system prompts.
- `prompt_addon` field contains the text.
- Applied via `inject_skills(_SYSTEM, state)` in every agent.
- `target_agents: []` means all agents.

**`agent_toggle`** — Disables an agent for a run (zero LLM cost).
- `enabled_agents` list is computed once at run start.
- `governed()` returns `{}` immediately for any agent not in `enabled_agents`.
- **Cannot target `planner` or `coder`** (validated at API layer).

### How skill context is computed:

`ui/backend/runs.py` `_compute_skill_context(overrides, db)`:
1. Load all `is_default=True` skills from DB
2. Build `effective[agent] = set(skill_ids)` for every agent in `_ALL_AGENTS`
3. Apply session `overrides` dict: `{agent_or_star: {add: [ids], remove: [ids]}}`
4. For each agent's effective skill set:
   - `prompt_injection` kinds → join `prompt_addon` texts → `skill_context[agent]`
   - `agent_toggle` kinds → add agent to `disabled` set
5. Return `(skill_context, [a for a in _ALL_AGENTS if a not in disabled])`

---

## 7. Threading model (critical)

The FastAPI event loop **must not** be blocked.

- `app.stream()` (the LangGraph sync generator) runs in a **worker thread** via `asyncio.to_thread(_run_pipeline_sync, ...)`.
- WebSocket events are published via `loop.call_soon_threadsafe(_put)` — never direct `queue.put_nowait()` from a thread.
- The approval gate blocks the **worker thread** using `asyncio.Event` + `run_coroutine_threadsafe` (NOT `await`) — this is correct because the gate runs inside the sync pipeline.
- `_main_loop` is stored at app startup (`asyncio.get_running_loop()`) so worker threads can schedule back onto it.

**Never call** `loop.run_until_complete()` or `asyncio.run()` inside a function that already runs in an event loop context.

---

## 8. Authentication & security invariants

These must NEVER be violated:

- `SECRET_KEY` must come from the environment — the server refuses to start if unset.
- Passwords are **bcrypt cost=12**, never logged, never in response bodies.
- JWT cookies: `httpOnly=True, secure=True, samesite="strict"`.
- Login returns the same `"Invalid credentials"` for wrong user or wrong password (no enumeration).
- API keys in `StartRunRequest.model_config.api_key` are **never written to the DB** — stripped before `db.create_run()`.
- WebSocket endpoint verifies run ownership (`db.get_run(run_id, user.user_id)`) before `await websocket.accept()`.
- Rate limiting keys on `X-Real-IP` / `X-Forwarded-For` (not proxy IP) — 5 login attempts per 15 minutes.
- CORS `allow_origins` comes from `ALLOWED_ORIGINS` env var — never `"*"` with credentials.

---

## 9. Configuration reference

### Environment variables (required)

| Variable | Where used | Notes |
|----------|-----------|-------|
| `SECRET_KEY` | `ui/backend/auth.py` | HS256 JWT signing key. `openssl rand -hex 32` |
| `POSTGRES_HOST` | `src/db/repo.py`, `src/graph.py` | Postgres hostname |
| `POSTGRES_PORT` | same | default `5432` |
| `POSTGRES_DB` | same | default `build_ship` |
| `POSTGRES_USER` | same | default `pipeline` |
| `POSTGRES_PASSWORD` | same | default `pipeline_secret` (change in prod) |
| `SEED_USERNAME` | `ui/backend/seed.py` | Admin username |
| `SEED_PASSWORD` | `ui/backend/seed.py` | Admin password (bcrypt-hashed at seed time) |

### Environment variables (optional)

| Variable | Default | Notes |
|----------|---------|-------|
| `ALLOWED_ORIGINS` | `""` (none) | CORS: `http://localhost:5173,http://localhost:8080` for dev |
| `ANTHROPIC_API_KEY` | — | Used by LiteLLM unless overridden per-run |
| `OPENAI_API_KEY` | — | Used by LiteLLM for OpenAI models |
| `GROQ_API_KEY` | — | Used by LiteLLM for Groq models |

### YAML config files

- **`config/budget.yaml`** — global ceilings and per-action hard caps for every run
- **`config/prices.yaml`** — USD per 1K tokens per model, default model per agent, expected output tokens

---

## 10. DB schema — 12 tables

| Table | Role | Key relationships |
|-------|------|-------------------|
| `memory` | Long-term cross-run memory (RAG source: past_plan/lesson/pattern) | standalone |
| `artifacts` | Generated file content (content_ref pointer keeps state slim) | `run_id → pipeline_runs` |
| `knowledge` | Shared context written/read by review agents (RAG source: known_cves/codebase_map) | `run_id` (implicit) |
| `audit_log` | Every agent decision | `run_id` |
| `budget_ledger` | Pre/post-flight cost rows | `run_id` |
| `users` | Auth — pre-seeded, no self-registration | standalone |
| `pipeline_runs` | One row per pipeline execution | `user_id → users` |
| `skills` | Skill definitions | standalone |
| `run_skill_overrides` | Per-session skill additions/removals | `run_id → pipeline_runs`, `skill_id → skills` |
| `rag_documents` | Chunked text corpus + GIN FTS index (+ optional pgvector embedding) | `doc_id` unique per chunk |
| `rag_entities` | Knowledge-graph nodes (file/function/class/service/concept) | unique `(corpus, name)` |
| `rag_relations` | Knowledge-graph edges (imports/calls/inherits/uses/defines) | `source_id`/`target_id → rag_entities` |

---

## 11. Frontend data flow

```
App.tsx
  ├── useRun() hook         — run state machine (idle/running/done/halted/stopped)
  ├── useWebSocket() hook   — WS /ws/runs/{id} → feeds events to useRun
  ├── Sidebar               — run history (polls /api/runs every 5s)
  ├── ChatWindow            — textarea + SessionSkills + execute → POST /api/runs
  │     └── SessionSkills   — skill overrides (lifted state in App.tsx)
  ├── StreamPanel           — reads runState: steps/budget/artifacts/findings
  ├── ApprovalGate          — modal when runState.approvalRequired=true
  └── SkillsManager         — slide-over, opened from Sidebar settings icon
```

WebSocket event types (defined in `src/types.ts`):
`step | budget | artifact | finding | approval_required | halt | done | error | ping`

---

## 12. Common tasks

### Run tests
```bash
pytest tests/unit/ -v
```

### Build frontend
```bash
cd ui/frontend && npm run build
```

### Seed the DB
```bash
SEED_USERNAME=admin SEED_PASSWORD=changeme python -m ui.backend.seed
```

### Start dev server (backend)
```bash
SECRET_KEY=devkey POSTGRES_HOST=localhost uvicorn ui.backend.app:app --reload --port 8080
```

### Apply DB schema
```bash
psql $DATABASE_URL -f src/db/schema.sql
```

### Create a skill via API
```bash
curl -s -b cookies.txt -X POST http://localhost:8080/api/skills \
  -H "Content-Type: application/json" \
  -d '{"id":"use-typescript","name":"Use TypeScript","kind":"prompt_injection","target_agents":["coder"],"prompt_addon":"Always write TypeScript, never plain JavaScript.","is_default":true}'
```

---

## 13. RAG layer (`src/rag/`)

Pluggable retrieval-augmented generation. Build a retriever with the factory,
index data, retrieve, then inject the formatted context into an agent prompt.

### Strategies (pass to `create_retriever(strategy=...)`)

| Strategy | Backend | LLM calls | Needs DB pool |
|----------|---------|-----------|---------------|
| `bm25` | in-memory Okapi BM25 | none | no |
| `bm25_pg` | Postgres GIN FTS (`ts_rank_cd`) | none | yes |
| `dense` | litellm embeddings + cosine | embed | no |
| `pgvector` | pgvector `<=>` | embed | yes (+ extension) |
| `hybrid` | RRF(bm25, dense) — **recommended** | embed | no |
| `hybrid_pg` | RRF(bm25_pg, pgvector) | embed | yes |
| `graph` / `graph_pg` | entity graph + BFS | extract+query | graph_pg only |
| `hyde` | hypothetical doc → dense | gen+embed | no |
| `multi_query` | N query variants + vote merge | gen | no |
| `reranked` | hybrid → LLM rerank | gen | no |

Every retriever from the factory is wrapped in `InstrumentedRetriever`
(`instrument=True` default) which adds OTel spans + metrics and validates
inputs via `src/rag/guards.py`. Pass `instrument=False` for raw retrievers.

### Observability (metrics in `src/observability/tracing.py`)

`rag_retrievals_total`, `rag_retrieval_seconds`, `rag_documents_indexed`,
`rag_empty_results`, `rag_rejected_inputs` — all labelled by `retriever`.
Spans: `rag.retrieve`, `rag.index`.

### Security guards (`src/rag/guards.py`)

- `validate_query` — non-empty, ≤ 8 000 chars
- `validate_k` — int in [1, 100] (rejects bool)
- `validate_corpus` — allowlist `^[a-z0-9_-]{1,64}$` (safe for SQL/labels)
- oversize chunks (> 100 KB) dropped at index time; content fed to LLMs truncated
- all DB SQL is parameterised; corpus names validated before use

### Use cases (`src/rag/recipes.py`) — cross-run learning loop

| Recipe | Agent | Source | What it does |
|--------|-------|--------|--------------|
| `retrieve_similar_plans` | planner | `memory(past_plan)` | reuse past decompositions |
| `retrieve_code_patterns` | coder | `memory(pattern)` | surface reusable patterns |
| `retrieve_debug_lessons` | debugger | `memory(lesson)` | recall fixes for similar failures |
| `retrieve_security_context` | security | `knowledge(known_cves, codebase_map)` | known CVEs + cross-file map |
| `persist_run_memory` | report | writes `memory` | persist plan + critical-finding lessons |

The loop: `report_node` calls `persist_run_memory()` at the end of a successful
run → future runs' planner/coder/debugger/security retrieve from it. All recipes
are wrapped so any DB/LLM error degrades to empty context (never crashes a run).
`db` is threaded into these nodes via lambdas in `graph.py`.
