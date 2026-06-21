"""governed() decorator that wraps every LangGraph node with budget enforcement."""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from src.config import PRICES_CFG
from src.governance.guard import BudgetExceeded, budget_guard, estimate_cost
from src.observability.tracing import halt_counter, record_agent_usage, tracer
from src.state import PipelineState


def governed(agent_name: str, db: Any = None) -> Callable:
    """Return a decorator that enforces budget constraints around a node function.

    The wrapped node function must have the signature:
        node_fn(state: PipelineState, model: str) -> tuple[dict, Usage]

    where Usage has attributes: .in_ (int), .out (int), .total (int).

    On BudgetExceeded the node returns a halt dict without making any LLM call.
    Model identity and custom endpoint/key are pulled from state["model_config"].
    """

    def decorator(node_fn: Callable) -> Callable:
        def inner(state: PipelineState) -> dict:
            # Skill: skip disabled agents (zero cost, no LLM call)
            enabled = state.get("enabled_agents")
            if enabled is not None and agent_name not in enabled:
                return {}

            # Resolve model from state config or default from prices config
            cfg = state.get("model_config") or {}
            model = cfg.get("model") or PRICES_CFG.model_for(agent_name)
            expected_out = PRICES_CFG.expected_out(agent_name)

            prompt_tokens = _estimate_prompt_tokens(agent_name, state)

            # Skill: inject per-agent prompt context into state for node to read
            skill_ctx = (state.get("skill_context") or {}).get(agent_name, "")
            if skill_ctx:
                state = {**state, "_skill_ctx": skill_ctx}  # type: ignore[assignment]

            with tracer.start_as_current_span(f"agent.{agent_name}") as span:
                span.set_attribute("run_id", state["run_id"])
                span.set_attribute("phase", state["phase"])
                span.set_attribute("model", model)
                span.set_attribute("step", state["budget"]["steps_taken"])

                # PRE-FLIGHT BUDGET CHECK
                try:
                    budget_guard(agent_name, model, prompt_tokens, expected_out, state, db)
                except BudgetExceeded as exc:
                    halt_counter.add(1, {"agent": agent_name, "reason": "budget"})
                    span.set_attribute("halted", True)
                    span.set_attribute("halt_reason", str(exc))
                    return {
                        "phase": "halted",
                        "halt_reason": str(exc),
                        "audit": [{"agent": agent_name, "halt": str(exc), "step": state["budget"]["steps_taken"]}],
                    }

                t0 = time.perf_counter()
                result, usage = node_fn(state, model)
                elapsed = time.perf_counter() - t0

                actual_cost = estimate_cost(model, usage.in_, usage.out)
                if db is not None:
                    db.reconcile_ledger(state["run_id"], agent_name, actual_cost)

                record_agent_usage(agent_name, usage.total, actual_cost, elapsed)
                span.set_attribute("tokens.total", usage.total)
                span.set_attribute("cost_usd", actual_cost)
                span.set_attribute("latency_s", elapsed)

                new_budget = {
                    **state["budget"],
                    "tokens_used": state["budget"]["tokens_used"] + usage.total,
                    "cost_used_usd": state["budget"]["cost_used_usd"] + actual_cost,
                    "steps_taken": state["budget"]["steps_taken"] + 1,
                }

                return {
                    **result,
                    "budget": new_budget,
                    "audit": [
                        {
                            "agent": agent_name,
                            "step": state["budget"]["steps_taken"],
                            "tokens": usage.total,
                            "cost_usd": actual_cost,
                            "latency_s": elapsed,
                        }
                    ],
                }

        inner.__name__ = node_fn.__name__
        return inner

    return decorator


def _estimate_prompt_tokens(agent: str, state: PipelineState) -> int:
    base = 500
    base += len(state.get("feature_request", "")) // 4
    base += len(str(state.get("plan", {}))) // 4
    base += len(state.get("findings", [])) * 50
    return base
