# Build & Ship Pipeline — Agent Knowledge Base

> **For any AI coding tool:** Read this folder before making changes to this repository.
> All relevant context for AI agents lives here. Start with this file, then read the
> specific files below based on your task.

---

## What is this project?

A **LangGraph multi-agent system** wrapped in a FastAPI + React web UI.
A user types a feature request; 12+ LLM agents collaborate to plan, code, test, review,
and report it — all within a hard budget ceiling and with full audit logging.

Three layers:
1. **Pipeline core** (`build-ship-pipeline/src/`) — LangGraph graph, agents, governance, DB
2. **Web UI backend** (`build-ship-pipeline/ui/backend/`) — FastAPI REST + WebSocket API
3. **Web UI frontend** (`build-ship-pipeline/ui/frontend/src/`) — React + Vite + Tailwind

---

## Files in this folder

| File | Read when... |
|------|-------------|
| `invariants.md` | **Always** — 5 critical rules that must never be violated |
| `architecture.md` | Understanding the pipeline topology, state schema, graph wiring |
| `coding-standards.md` | Writing or reviewing Python / TypeScript code |
| `security.md` | Touching auth, API endpoints, DB queries, or any security-sensitive code |
| `common-tasks.md` | Running tests, seeding DB, starting the dev server, building the frontend |
| `skills/` | Skill definitions seeded into the pipeline DB as system defaults |

---

## 5-second orientation

```
agents/
├── README.md           ← you are here
├── architecture.md     ← graph topology, state fields, governed() decorator
├── invariants.md       ← 5 rules that must never be broken
├── coding-standards.md ← type hints, async, logging, SQL, Pydantic v2
├── security.md         ← 8 auth/security invariants
├── common-tasks.md     ← quick commands (pytest, seed, build, dev server)
└── skills/             ← 20 YAML skill files → seeded to DB as system skills
```

The full reference is `build-ship-pipeline/CLAUDE.md`.

---

## Quick invariants (read invariants.md for details and code examples)

1. **Add-reducer** — `artifacts`/`findings`/`audit` return ONLY new items, never the full list
2. **governed() wrapper** — every graph node must be wrapped: `governed("name", db)(fn)`
3. **Budget ceiling** — $5 / 2M tokens / 120 steps, hard-enforced
4. **Threading** — pipeline runs in a worker thread; never call `asyncio.run()` inside pipeline code
5. **Return type** — every node returns `(dict, Usage)`, never just `dict`
