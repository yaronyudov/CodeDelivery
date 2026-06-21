"""Planner agent — decomposes the feature request into a build plan."""
from __future__ import annotations

import json

from src.agents.base import Usage, call_model
from src.state import PipelineState

_SYSTEM = """You are the Planner agent in a software build pipeline.
Given a feature request, produce a structured build plan as JSON with these keys:
- summary: one-sentence description
- tasks: list of {id, title, description, owner} where owner is one of
  [coder, docker, observability, tester]
- tech_stack: list of technologies needed
- complexity: float between 0.5 and 3.0 (0.5=trivial, 3.0=very complex)
- acceptance_criteria: list of strings

Respond ONLY with valid JSON, no prose."""


def planner_node(state: PipelineState, model: str) -> tuple[dict, Usage]:
    user_msg = f"Feature request:\n{state['feature_request']}"

    if state.get("findings"):
        critical = [f for f in state["findings"] if f["severity"] in ("critical", "major")]
        if critical:
            findings_text = "\n".join(f"- [{f['agent']}] {f['message']}" for f in critical)
            user_msg += f"\n\nPrevious review found critical issues — revise plan:\n{findings_text}"

    text, usage = call_model(model, _SYSTEM, user_msg)

    try:
        plan = json.loads(text)
    except json.JSONDecodeError:
        plan = {"summary": text, "tasks": [], "tech_stack": [], "complexity": 1.0, "acceptance_criteria": []}

    return {
        "plan": plan,
        "tech_stack": plan.get("tech_stack", []),
        "phase": "dev",
    }, usage
