"""Budget guard: pre-flight enforcement before every model call."""

from __future__ import annotations

from src.config import PRICES_CFG
from src.governance.dynamic import compute_dynamic_caps
from src.state import PipelineState


class BudgetExceeded(Exception):
    """Raised when a pre-flight budget check fails."""


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Estimate USD cost for a call given token counts."""
    in_price, out_price = PRICES_CFG.price_per_1k(model)
    return (tokens_in / 1000) * in_price + (tokens_out / 1000) * out_price


def budget_guard(
    agent: str,
    model: str,
    prompt_tokens: int,
    expected_out: int,
    state: PipelineState,
    db=None,  # optional db repo injected at call site
) -> None:
    """Run all pre-flight budget checks.  Raises BudgetExceeded on any failure.

    Checks (in order):
      1. Step limit
      2. Dynamic per-action token cap
      3. Dynamic per-action money cap
      4. Global cost ceiling would not be crossed
    """
    b = state["budget"]

    # 1. STEP LIMIT
    if b["steps_taken"] >= b["steps_limit"]:
        raise BudgetExceeded(f"step limit reached ({b['steps_taken']}/{b['steps_limit']})")

    # 2. Recompute dynamic caps for this specific action
    tok_cap, cost_cap = compute_dynamic_caps(state, agent)

    # 3. PER-ACTION TOKEN CAP
    total_tokens = prompt_tokens + expected_out
    if total_tokens > tok_cap:
        raise BudgetExceeded(f"{agent}: token estimate {total_tokens} > per-action cap {tok_cap}")

    # 4. PER-ACTION MONEY CAP (pre-flight estimate)
    est = estimate_cost(model, prompt_tokens, expected_out)
    if est > cost_cap:
        raise BudgetExceeded(f"{agent}: est ${est:.4f} > per-action cap ${cost_cap:.4f}")

    # 5. GLOBAL cost ceiling would be crossed
    if b["cost_used_usd"] + est > b["cost_limit_usd"]:
        raise BudgetExceeded(
            f"global cost limit would be exceeded "
            f"(used ${b['cost_used_usd']:.4f} + est ${est:.4f} "
            f"> limit ${b['cost_limit_usd']:.4f})"
        )

    # Persist a pre-flight ledger row if db is available
    if db is not None:
        db.insert_budget_ledger(
            run_id=state["run_id"],
            step=b["steps_taken"],
            agent=agent,
            model=model,
            tokens_in=prompt_tokens,
            tokens_out=expected_out,
            est_cost_usd=est,
            allowed=True,
        )
