# Build & Ship Pipeline — Agent Knowledge Base

> **For any AI coding tool:** Read this folder before making changes to this repository.
> All relevant context for AI agents lives here. Start with this file, then read the
> specific files below based on your task.
>
> **When you make a change, you must update the docs it affects** — see
> [When you make a change](#when-you-make-a-change-required) below.

---

## When you make a change (required)

Documentation is part of the change, not a follow-up. Whenever you modify the code,
update the relevant docs **in the same commit / PR** so this knowledge base never drifts:

| If you change... | Update... |
|------------------|-----------|
| The agent graph, state fields, or reducers | `agents/architecture.md` and `build-ship-pipeline/CLAUDE.md` |
| A critical rule, decorator, or threading model | `agents/invariants.md` |
| Coding conventions (Python / TypeScript) | `agents/coding-standards.md` |
| Auth, API, DB, or any security-sensitive code | `agents/security.md` |
| Commands, scripts, or dependencies | `agents/common-tasks.md` |
| Skill definitions | the YAML in `agents/skills/` (the seeder reads these files) |
| Anything user-facing or architectural | the relevant tool convention files at the repo root |

Rules:
1. **Keep facts accurate.** If a doc states a number, command, or signature, verify it
   still matches the code (e.g. test counts, budget ceilings, function signatures).
2. **No silent drift.** A PR that changes behaviour but not the docs that describe it is
   incomplete.
3. **Docs and convention files are derived from this folder** — when you update a fact
   here, update the matching summary in `AGENTS.md`, `.cursor/rules/*.mdc`,
   `.windsurfrules`, `.clinerules`, and `.github/copilot-instructions.md` if they repeat it.

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
