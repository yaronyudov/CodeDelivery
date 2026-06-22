# Build & Ship Pipeline — AI Agent Instructions

> **Read this before making any changes to this repository.**
> Then read the `agents/` folder for full context.

---

## Go to the agents/ folder

All context for AI coding agents is in the **`agents/` folder** at the repo root.

```
agents/
├── README.md           ← start here
├── invariants.md       ← 5 critical rules (read always)
├── architecture.md     ← graph topology, state schema, governed() decorator
├── coding-standards.md ← type hints, async, SQL, Pydantic v2, logging
├── security.md         ← 8 auth/security invariants
├── common-tasks.md     ← pytest, seed, build, dev server commands
└── skills/             ← 20 YAML skill definitions (seeded to DB as system skills)
```

---

## What this project is

A LangGraph multi-agent pipeline + FastAPI backend + React frontend.
A user types a feature request; 12 LLM agents plan, code, test, and review it
under a hard budget ceiling with full audit logging.

Main source: `build-ship-pipeline/`
Full reference: `build-ship-pipeline/CLAUDE.md`

---

## 5 rules that must never be broken

1. **Add-reducer** — `artifacts`/`findings`/`audit` return ONLY new items (never full list)
2. **governed() wrapper** — every node: `governed("name", db)(fn)` in graph.py
3. **Budget ceiling** — $5 / 2M tokens / 120 steps, hard-enforced by budget_guard()
4. **No asyncio.run()** — pipeline runs in a worker thread; never nest event loops
5. **Return (dict, Usage)** — every node returns a 2-tuple, never just dict

See `agents/invariants.md` for code examples of each.

---

## System skills

The `agents/skills/` folder contains 20 YAML files defining the pipeline's built-in skills.
These are seeded to the Postgres DB as `is_system=True` skills via:

```bash
SEED_USERNAME=admin SEED_PASSWORD=changeme python -m ui.backend.seed
```

Skills can be activated, disabled, or overridden per run via the web UI or `/api/skills`.

---

## Keep docs in sync (required)

When you change behaviour, update the docs it affects **in the same commit/PR**. Map of
what to update lives in `agents/README.md` → *When you make a change*. In short: graph/state
→ `agents/architecture.md`; rules → `agents/invariants.md`; conventions →
`agents/coding-standards.md`; auth/API/DB → `agents/security.md`; commands/deps →
`agents/common-tasks.md`; skills → `agents/skills/*.yml`. Always verify stated facts (test
counts, budget ceilings, signatures) still match the code. A change that updates code but
not its docs is incomplete.
