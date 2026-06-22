# Critical Invariants

These 5 rules must never be violated. They are checked by the governed() decorator,
the LangGraph state reducers, and the budget guard. Breaking them causes silent data
loss, double-counting, or crashes at scale.

---

## 1. Add-reducer rule (MOST COMMON BUG)

`artifacts`, `findings`, and `audit` in `PipelineState` use LangGraph **add-reducers**.
This means LangGraph automatically merges lists — do NOT return the full accumulated list.

```python
# WRONG — duplicates every item already in state
return {"findings": state["findings"] + [new_finding]}, usage

# CORRECT — return only the new item(s)
return {"findings": [new_finding]}, usage
```

Fields affected: `artifacts`, `findings`, `audit` (all `Annotated[list, add]` in state.py).
All other list fields use replace semantics — return the full new value.

---

## 2. governed() wrapper — every node must use it

Every agent function is registered in `graph.py` through `governed()`:

```python
# graph.py
from src.governance.governed import governed

g.add_node("myagent", governed("myagent", db)(myagent_node))
```

`governed()` provides: skill toggle, budget pre-flight check, model resolution,
skill context injection (`_skill_ctx`), OTel span, cost reconciliation, audit append.
Never register a raw node function directly — it bypasses all governance.

---

## 3. Budget ceiling — hard enforced

Every run has a hard ceiling: **$5 / 2 000 000 tokens / 120 steps** (from `config/budget.yaml`).
`budget_guard()` raises `BudgetExceeded` before a node call if the ceiling would be exceeded.
When `BudgetExceeded` is raised, `governed()` catches it and returns `{"phase": "halted", ...}`.
This routes the graph to `halt_node → END`.

Never suppress `BudgetExceeded`. Never `try/except BudgetExceeded: pass`.

---

## 4. Threading model — no asyncio.run() inside pipeline code

The LangGraph pipeline (`app.stream(...)`) runs in a **worker thread** via `asyncio.to_thread()`.
The FastAPI event loop runs in the main thread.

```python
# WRONG — asyncio.run() inside a function already scheduled in a thread
def myagent_node(state, model):
    result = asyncio.run(some_async_fn())   # raises RuntimeError

# CORRECT — call sync variants, or use asyncio.to_thread in the outer layer
def myagent_node(state, model):
    result = some_sync_fn()
```

WebSocket publishes back to the main loop via `loop.call_soon_threadsafe()`.
The approval gate blocks the worker thread with `asyncio.Event` + `run_coroutine_threadsafe`.

---

## 5. Node return type — always (dict, Usage)

Every agent node function must return a 2-tuple:

```python
from src.agents.base import Usage

def myagent_node(state: PipelineState, model: str) -> tuple[dict, Usage]:
    text, usage = call_model(model, system_prompt, user_msg)
    return {"my_output_field": text}, usage
    #       ^ dict of state updates   ^ Usage(in_=N, out=M)
```

`governed()` reads the second element to reconcile costs. Returning just a dict,
returning `None`, or returning `(dict, None)` will cause a `TypeError` at runtime.
