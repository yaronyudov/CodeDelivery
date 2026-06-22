# Build & Ship Pipeline — GitHub Copilot Instructions

Read the `agents/` folder at the repo root before suggesting code changes.

## Project summary

LangGraph multi-agent pipeline (12 agents) + FastAPI backend + React frontend.
Agents collaborate to plan, code, test, and review features under a hard budget ceiling.

## Critical rules for code suggestions

### LangGraph state (most common source of bugs)
- `artifacts`, `findings`, `audit` use **add-reducers** — return ONLY new items, never the full list
- Node signature: `def node(state: PipelineState, model: str) -> tuple[dict, Usage]:`
- Every node in graph.py must be wrapped: `governed("name", db)(node_fn)`

### Python conventions
- Full type annotations + `from __future__ import annotations`
- Pydantic v2 syntax: `model_config = ConfigDict(...)`, `model_validate()`, `model_dump()`
- Async for I/O; never `asyncio.run()` inside pipeline code (runs in a worker thread)
- Parameterized SQL only — never f-string queries
- `logging` not `print()`

### Security (never violate)
- `SECRET_KEY` from env; bcrypt cost≥12; httpOnly+secure+samesite cookies
- Strip `api_key` from `model_config` before `db.create_run()`
- CORS `allow_origins` from env var; never `"*"` with credentials
- Verify run ownership before WebSocket accept

## PR review checklist
- [ ] No add-reducer violations (full list returned for artifacts/findings/audit)
- [ ] governed() wrapper present for all new graph nodes
- [ ] No asyncio.run() inside pipeline functions
- [ ] Return type is (dict, Usage), not just dict
- [ ] Parameterized SQL throughout
- [ ] No hardcoded secrets or API keys
- [ ] Security invariants from agents/security.md preserved

## Key files

```
agents/                         ← universal agent knowledge base (read first)
build-ship-pipeline/CLAUDE.md   ← full authoritative reference
build-ship-pipeline/src/state.py         ← PipelineState + _ALL_AGENTS
build-ship-pipeline/src/graph.py         ← graph wiring
build-ship-pipeline/src/governance/governed.py  ← governed() decorator
```
