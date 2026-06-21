"""Governance layer unit tests — all pass without any LLM calls."""

import pytest

from src.governance.dynamic import ROLE_WEIGHTS, compute_dynamic_caps
from src.governance.guard import BudgetExceeded, budget_guard, estimate_cost
from src.state import initial_state

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state(
    steps_taken=0,
    tokens_used=0,
    cost_used=0.0,
    steps_limit=120,
    tokens_limit=2_000_000,
    cost_limit=5.0,
    complexity=1.0,
):
    s = initial_state("run-test", "test feature")
    s["budget"] = {
        **s["budget"],
        "tokens_limit": tokens_limit,
        "cost_limit_usd": cost_limit,
        "steps_limit": steps_limit,
        "tokens_used": tokens_used,
        "cost_used_usd": cost_used,
        "steps_taken": steps_taken,
        "per_action_token_cap": 0,
        "per_action_cost_cap_usd": 0.0,
    }
    s["plan"] = {"complexity": complexity}
    return s


# ---------------------------------------------------------------------------
# estimate_cost
# ---------------------------------------------------------------------------


def test_estimate_cost_known_model():
    cost = estimate_cost("claude-haiku-4-5-20251001", 1000, 500)
    # 1K input * 0.00025 + 0.5K output * 0.00125 = 0.25 + 0.625 = 0.875 mUSD
    assert cost == pytest.approx((1 * 0.00025) + (0.5 * 0.00125), rel=1e-6)


def test_estimate_cost_zero_tokens():
    assert estimate_cost("claude-haiku-4-5-20251001", 0, 0) == 0.0


# ---------------------------------------------------------------------------
# compute_dynamic_caps
# ---------------------------------------------------------------------------


def test_dynamic_caps_tighten_as_budget_depletes():
    # Simulate fast budget burn: same steps remaining, much less budget left.
    # full: 10 steps, 100K tokens, $0.20
    s_full = _state(
        tokens_used=0,
        cost_used=0.0,
        steps_taken=0,
        steps_limit=10,
        tokens_limit=100_000,
        cost_limit=0.20,
    )
    # burned: 8 steps used, but burned 95K tokens/$0.19 (fast burn)
    # only 5K tokens and $0.01 left for the last 2 steps
    s_burned = _state(
        tokens_used=95_000,
        cost_used=0.19,
        steps_taken=8,
        steps_limit=10,
        tokens_limit=100_000,
        cost_limit=0.20,
    )

    tok_full, cost_full = compute_dynamic_caps(s_full, "coder")
    tok_burned, cost_burned = compute_dynamic_caps(s_burned, "coder")

    assert tok_burned < tok_full
    assert cost_burned < cost_full


def test_dynamic_caps_respect_hard_ceilings():
    # Even with a huge budget, caps never exceed hard ceilings
    s = _state(tokens_limit=100_000_000, cost_limit=1000.0, steps_limit=1, complexity=3.0)
    from src.config import BUDGET_CFG

    tok_cap, cost_cap = compute_dynamic_caps(s, "coder")
    assert tok_cap <= BUDGET_CFG.hard_action_token_ceil
    assert cost_cap <= BUDGET_CFG.hard_action_cost_ceil_usd


def test_dynamic_caps_scale_with_role_weight():
    s = _state()
    tok_coder, _ = compute_dynamic_caps(s, "coder")  # weight 1.5
    tok_style, _ = compute_dynamic_caps(s, "style")  # weight 0.4
    assert tok_coder > tok_style


def test_all_roles_have_weights():
    for role in [
        "planner",
        "coder",
        "docker",
        "observability",
        "tester",
        "debugger",
        "reviewer",
        "review_sup",
        "security",
        "perf",
        "style",
        "coverage",
    ]:
        assert role in ROLE_WEIGHTS, f"Missing ROLE_WEIGHTS entry for {role!r}"


# ---------------------------------------------------------------------------
# budget_guard — happy path
# ---------------------------------------------------------------------------


def test_budget_guard_passes_with_plenty_of_budget():
    s = _state()
    # Should not raise
    budget_guard("coder", "claude-haiku-4-5-20251001", 500, 500, s)


# ---------------------------------------------------------------------------
# budget_guard — step limit
# ---------------------------------------------------------------------------


def test_budget_guard_blocks_on_step_limit():
    s = _state(steps_taken=120, steps_limit=120)
    with pytest.raises(BudgetExceeded, match="step limit"):
        budget_guard("coder", "claude-haiku-4-5-20251001", 100, 100, s)


def test_budget_guard_allows_at_step_limit_minus_one():
    s = _state(steps_taken=119, steps_limit=120)
    budget_guard("coder", "claude-haiku-4-5-20251001", 100, 100, s)


# ---------------------------------------------------------------------------
# budget_guard — token cap
# ---------------------------------------------------------------------------


def test_budget_guard_blocks_on_token_cap():
    # Nearly exhausted budget so dynamic cap is tiny
    s = _state(
        tokens_used=1_999_900,
        cost_used=4.99,
        steps_taken=119,
        steps_limit=120,
        tokens_limit=2_000_000,
        cost_limit=5.0,
    )
    with pytest.raises(BudgetExceeded, match="token estimate"):
        budget_guard("coder", "claude-haiku-4-5-20251001", 50_000, 50_000, s)


# ---------------------------------------------------------------------------
# budget_guard — global cost ceiling
# ---------------------------------------------------------------------------


def test_budget_guard_blocks_when_global_cost_would_be_exceeded():
    # 1 step remaining + complexity=2.0 → per-action cap = $0.10 * 1 * 1.5 * 2 = $0.30
    # Only $0.10 remains globally, so a $0.15 call passes per-action but fails globally.
    # est = (5000/1000)*$0.003 + (9000/1000)*$0.015 = $0.015 + $0.135 = $0.15
    s = _state(cost_used=4.90, cost_limit=5.0, steps_taken=119, steps_limit=120, complexity=2.0)
    with pytest.raises(BudgetExceeded, match="global cost limit"):
        budget_guard("coder", "claude-sonnet-4-6", 5000, 9000, s)


# ---------------------------------------------------------------------------
# governed() — halt path (no real LLM call)
# ---------------------------------------------------------------------------


def test_governed_returns_halt_when_budget_exceeded():
    from src.governance.governed import governed

    def fake_node(state, model):
        raise AssertionError("Should never be called")

    s = _state(steps_taken=120, steps_limit=120)
    wrapped = governed("coder")(fake_node)
    result = wrapped(s)

    assert result["phase"] == "halted"
    assert "halt_reason" in result
    assert len(result["audit"]) == 1
    assert result["audit"][0]["agent"] == "coder"


def test_governed_calls_node_when_budget_ok():
    from src.agents.base import Usage
    from src.governance.governed import governed

    called = []

    def fake_node(state, model):
        called.append(model)
        return {"phase": "dev"}, Usage(in_=10, out=10)

    s = _state()
    wrapped = governed("coder")(fake_node)
    result = wrapped(s)
    assert called, "node was never called"
    assert result.get("phase") == "dev"
    # Budget counters should be incremented
    assert result["budget"]["steps_taken"] == 1
    assert result["budget"]["tokens_used"] == 20
