# Coding Standards

These standards apply to all Python and TypeScript code in this repository.

---

## Python

### Type hints (mandatory)

```python
from __future__ import annotations

def process(items: list[str], limit: int = 10) -> dict[str, int]:
    ...
```

- Every function must have parameter and return type annotations.
- Use `from __future__ import annotations` at the top of every module.
- Never use bare `Any` — prefer `TypeVar`, `Protocol`, or explicit union types.
- Run `mypy --strict` mentally before outputting code.

### Pydantic v2

```python
# Correct v2 syntax
from pydantic import BaseModel, ConfigDict, Field

class MyModel(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str = Field(min_length=1)

instance = MyModel.model_validate({"name": "foo"})
data = instance.model_dump()
```

Never use: `class Config:`, `.parse_obj()`, `.dict()`, `@validator`, `pydantic.v1`.

### Async I/O

- I/O-bound operations must be `async` (use `httpx`, `aiofiles`, psycopg3 async interface).
- Never call blocking I/O (`requests`, `open()`, `time.sleep()`) inside `async def`.
- Use `asyncio.to_thread()` to bridge sync-only libraries from async context.
- Never call `asyncio.run()` inside pipeline node functions (see `invariants.md §4`).

### Logging

```python
import logging
logger = logging.getLogger(__name__)

logger.info("Run started", extra={"run_id": run_id})
# NEVER: print(f"Run started: {run_id}")
```

- No `print()` in production code. Use `logging` at appropriate levels.
- Never log passwords, tokens, JWTs, or PII. Redact before logging.

### SQL

```python
# ALWAYS parameterized
cursor.execute("SELECT * FROM runs WHERE user_id = %s AND id = %s", (user_id, run_id))

# NEVER f-strings or concatenation
cursor.execute(f"SELECT * FROM runs WHERE id = {run_id}")  # SQL injection risk
```

Column/table names cannot be parameterized — validate against an allowlist before use.
Corpus names must match `^[a-z0-9_-]{1,64}$`.

### Import order

1. `from __future__ import annotations`
2. stdlib
3. third-party (pydantic, fastapi, langgraph, litellm, psycopg3…)
4. local (`from src.`, `from ui.backend.`)

Use `ruff` for formatting and linting. Line length: 100.

---

## TypeScript (frontend)

### Strict mode

```json
// tsconfig.json
{ "compilerOptions": { "strict": true } }
```

No `as any`. Use `unknown` for untyped external data, then narrow with type guards.

### Component props

```tsx
interface RunCardProps {
  run: RunSummary;
  onSelect: (id: string) => void;
}

export function RunCard({ run, onSelect }: RunCardProps) { ... }
```

All component props must have an interface. No implicit prop types.

### Async functions

```ts
async function fetchRun(id: string): Promise<RunSummary> {
  const res = await fetch(`/api/runs/${id}`, { credentials: "include" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<RunSummary>;
}
```

All async functions must have explicit return type annotations.

---

## File naming

| Context | Convention | Example |
|---------|-----------|---------|
| Python modules | `snake_case.py` | `budget_guard.py` |
| Python tests | `test_<module>.py` | `test_governance.py` |
| React components | `PascalCase.tsx` | `StreamPanel.tsx` |
| React hooks | `useCamelCase.ts` | `useWebSocket.ts` |
| API modules | `snake_case.ts` | `runs.ts` |

---

## Documentation (part of every change)

Docs are not a follow-up task — they ship with the code that changes them.

- **Update docs in the same commit/PR as the code.** A behaviour change without the
  matching doc update is an incomplete change.
- **Verify facts against the code.** Numbers, commands, and signatures stated in docs
  (test counts, budget ceilings, function signatures) must still match reality.
- **Where to update** — see the mapping table in `agents/README.md` →
  *When you make a change*. In short: graph/state → `architecture.md`; rules →
  `invariants.md`; conventions → `coding-standards.md`; auth/API/DB → `security.md`;
  commands/deps → `common-tasks.md`; skills → `agents/skills/*.yml`.
- **Keep derived files in sync.** When a fact in `agents/` changes, update the summaries
  that repeat it in `AGENTS.md`, `.cursor/rules/*.mdc`, `.windsurfrules`, `.clinerules`,
  `.github/copilot-instructions.md`, and `build-ship-pipeline/CLAUDE.md`.
- **Public API or env-var changes** must also update `README`/setup docs and `.env.example`.
