"""Dynamic per-action cap computation based on remaining budget and agent role."""

from __future__ import annotations

from src.config import BUDGET_CFG
from src.state import PipelineState

# Relative token/cost weight per agent role.
# Higher = this agent is allowed a bigger slice of the remaining budget.
ROLE_WEIGHTS: dict[str, float] = {
    "planner": 1.0,
    "coder": 1.5,
    "docker": 0.8,
    "observability": 0.9,
    "tester": 0.7,
    "debugger": 1.2,
    "reviewer": 0.6,
    "review_sup": 0.5,
    "security": 0.8,
    "perf": 0.8,
    "style": 0.4,
    "coverage": 0.6,
}

_HARD_TOKEN_CEIL = BUDGET_CFG.hard_action_token_ceil
_HARD_COST_CEIL = BUDGET_CFG.hard_action_cost_ceil_usd


def compute_dynamic_caps(state: PipelineState, agent: str) -> tuple[int, float]:
    """Return (token_cap, cost_cap_usd) for a single action by *agent*.

    Caps tighten as the global budget depletes and scale with task complexity
    and the agent's role weight.
    """
    b = state["budget"]
    remaining_tokens = b["tokens_limit"] - b["tokens_used"]
    remaining_cost = b["cost_limit_usd"] - b["cost_used_usd"]
    remaining_steps = max(1, b["steps_limit"] - b["steps_taken"])

    weight = ROLE_WEIGHTS.get(agent, 1.0)
    complexity = float(state.get("plan", {}).get("complexity", 1.0))  # 0.5–3.0

    # Fair share of what remains, scaled by weight and task complexity
    fair_share = 1.0 / remaining_steps
    token_cap = int(remaining_tokens * fair_share * weight * complexity)
    cost_cap = remaining_cost * fair_share * weight * complexity

    # Clamp to absolute hard ceilings so a single action can never dominate
    token_cap = min(token_cap, _HARD_TOKEN_CEIL)
    cost_cap = min(cost_cap, _HARD_COST_CEIL)

    return token_cap, cost_cap
