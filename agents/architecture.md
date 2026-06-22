# Pipeline Architecture

## Graph topology

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

Any node can return phase="halted" → routes to halt_node → END
```

**Routing rules:**
- `approval_gate`: if `require_approval=False`, returns `approval_status="approved"` immediately
- `tester`: loops to `debugger` up to `BUDGET_CFG.debug_max_attempts` times (default 3), then escalates
- `review_verdict`: critical verdict sends everything back to `planner` for a full redo
- `BudgetExceeded` in any node → `{"phase": "halted", "halt_reason": ...}` → `halt_node`

---

## Agent list (`_ALL_AGENTS` in src/state.py)

| Agent | Role | Phase |
|-------|------|-------|
| `planner` | Decompose feature → plan + tech_stack | dev |
| `coder` | Implement the plan → artifacts | dev |
| `docker` | Generate Docker Compose config | dev |
| `observability` | Add OTel instrumentation | dev |
| `tester` | Run tests, report pass/fail | dev |
| `debugger` | Fix failing tests | dev |
| `reviewer` | Overall code quality review | review |
| `review_supervisor` | Route to specialist reviewers | review |
| `security` | OWASP Top 10 + CVE check | review |
| `perf` | Latency / memory / throughput analysis | review |
| `style` | Linting, naming, conventions | review |
| `coverage` | Test coverage analysis | review |

---

## PipelineState fields

| Field | Type | Reducer | Notes |
|-------|------|---------|-------|
| `run_id` | `str` | replace | UUID |
| `feature_request` | `str` | replace | User input, immutable |
| `phase` | `Literal` | replace | `"dev"` → `"review"` → `"done"/"halted"` |
| `plan` | `dict` | replace | Planner output |
| `tech_stack` | `list[str]` | replace | Planner output |
| `artifacts` | `list[Artifact]` | **add** | Return ONLY new items |
| `test_results` | `dict` | replace | Latest tester output |
| `debug_attempts` | `int` | replace | Incremented by debugger |
| `findings` | `list[Finding]` | **add** | Return ONLY new items |
| `verdict` | `str\|None` | replace | Set by review_verdict |
| `budget` | `Budget` | replace | Updated by governed() |
| `audit` | `list[dict]` | **add** | Return ONLY new items |
| `halt_reason` | `str\|None` | replace | Set when phase→halted |
| `require_approval` | `bool` | replace | From StartRunRequest |
| `approval_status` | `str\|None` | replace | Managed by approval_gate_node |
| `model_config` | `dict` | replace | {provider, model, api_base, api_key} |
| `skill_context` | `dict` | replace | {agent_name: combined_prompt_text} |
| `enabled_agents` | `list` | replace | Agents minus disabled toggles |
| `_skill_ctx` | `str` | replace | Internal — set by governed() per call |

---

## Key source files

| File | Purpose |
|------|---------|
| `src/state.py` | `PipelineState` TypedDict + `initial_state()` + `_ALL_AGENTS` |
| `src/graph.py` | StateGraph wiring — nodes, edges, conditional routers |
| `src/agents/base.py` | `call_model()`, `inject_skills()`, `model_kwargs_from_state()` |
| `src/governance/governed.py` | `governed()` decorator (skill toggle + budget + tracing) |
| `src/governance/guard.py` | `budget_guard()`, `BudgetExceeded`, `estimate_cost()` |
| `src/db/repo.py` | `PipelineRepo` — all DB access (psycopg3 pool) |
| `src/db/schema.sql` | 12-table Postgres schema |
| `ui/backend/runs.py` | `/api/runs` endpoints + `_compute_skill_context()` |
| `ui/backend/seed.py` | DB seeder — reads `agents/skills/*.yml` |
| `config/budget.yaml` | Hard ceilings: $5 / 2M tokens / 120 steps |
| `config/prices.yaml` | USD/1K tokens + default model per agent |

---

## How to add a new agent

1. Create `src/agents/dev/myagent.py`:
   ```python
   from src.agents.base import Usage, call_model, inject_skills, model_kwargs_from_state
   from src.state import PipelineState

   _SYSTEM = "You are the MyAgent agent..."

   def myagent_node(state: PipelineState, model: str) -> tuple[dict, Usage]:
       text, usage = call_model(
           model, inject_skills(_SYSTEM, state), f"Input: {state['some_field']}",
           **model_kwargs_from_state(state)
       )
       return {"some_output_field": text}, usage
   ```

2. Add `"myagent"` to `_ALL_AGENTS` in `src/state.py`

3. Wire into graph in `src/graph.py`:
   ```python
   g.add_node("myagent", governed("myagent", db)(myagent_node))
   g.add_edge("previous_node", "myagent")
   ```

4. Add default model in `config/prices.yaml` under `agent_models` and `expected_output_tokens`
