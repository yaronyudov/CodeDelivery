# Common Tasks

All commands run from `build-ship-pipeline/` unless noted otherwise.

---

## Run tests

```bash
pytest tests/unit/ -v
```

Tests are unit tests only — no live DB or LLM calls required.
The 16 tests cover governance, state, and budget logic.

---

## Lint and format

```bash
ruff check src/ tests/ ui/backend/
ruff format src/ tests/ ui/backend/
```

Line length: 100. Config in `pyproject.toml`.

---

## Build frontend

```bash
cd ui/frontend && npm run build
```

Output goes to `ui/frontend/dist/` — served by FastAPI as a SPA fallback.

---

## Seed the database

```bash
SEED_USERNAME=admin SEED_PASSWORD=changeme python -m ui.backend.seed
```

Idempotent — safe to run multiple times. Creates the admin user and all 20 system skills.
Skills are loaded from `agents/skills/*.yml` (relative to repo root).

---

## Apply the DB schema

```bash
psql $DATABASE_URL -f src/db/schema.sql
```

Run once on a fresh database. The schema is idempotent (uses `CREATE TABLE IF NOT EXISTS`).

---

## Start the dev backend

```bash
SECRET_KEY=devkey POSTGRES_HOST=localhost \
  uvicorn ui.backend.app:app --reload --port 8080
```

The frontend dev server (Vite) runs separately:
```bash
cd ui/frontend && npm run dev   # http://localhost:5173
```

Set `ALLOWED_ORIGINS=http://localhost:5173` so CORS works during development.

---

## Start everything with Docker Compose

```bash
docker compose up
```

Starts: Postgres, OTel collector, Prometheus, Loki, Tempo, Grafana, FastAPI backend, nginx.

---

## Create a skill via API

```bash
curl -s -b cookies.txt -X POST http://localhost:8080/api/skills \
  -H "Content-Type: application/json" \
  -d '{
    "id": "use-typescript",
    "name": "Use TypeScript",
    "kind": "prompt_injection",
    "target_agents": ["coder"],
    "prompt_addon": "Always write TypeScript, never plain JavaScript.",
    "is_default": true
  }'
```

---

## Re-seed skills after adding a new YAML file

```bash
SEED_USERNAME=admin SEED_PASSWORD=changeme python -m ui.backend.seed
```

New skills in `agents/skills/*.yml` are picked up automatically. Existing skills are skipped.

---

## Environment variables reference

| Variable | Required | Notes |
|----------|----------|-------|
| `SECRET_KEY` | Yes | HS256 JWT key — `openssl rand -hex 32` |
| `POSTGRES_HOST` | Yes | Postgres hostname |
| `POSTGRES_PORT` | No | Default: `5432` |
| `POSTGRES_DB` | No | Default: `build_ship` |
| `POSTGRES_USER` | No | Default: `pipeline` |
| `POSTGRES_PASSWORD` | No | Default: `pipeline_secret` (change in prod) |
| `SEED_USERNAME` | Seed only | Admin username |
| `SEED_PASSWORD` | Seed only | Admin password |
| `ALLOWED_ORIGINS` | No | CORS origins, comma-separated |
| `ANTHROPIC_API_KEY` | No | Used by LiteLLM for Claude models |
| `OPENAI_API_KEY` | No | Used by LiteLLM for OpenAI models |
