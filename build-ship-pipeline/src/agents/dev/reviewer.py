"""Internal Reviewer agent — final dev-phase sign-off before review phase."""
from __future__ import annotations

import json

from src.agents.base import Usage, call_model, inject_skills, model_kwargs_from_state
from src.state import PipelineState

_SYSTEM = """You are the Internal Reviewer agent in a software build pipeline.
Perform a quick sanity check on the build artifacts before entering the
formal review phase.

Respond with a JSON object:
{
  "approved": true,
  "notes": "brief assessment"
}

Approve if:
- There are artifacts produced (code, compose, tests)
- Tests passed
- No obvious showstopper issues

Respond ONLY with this JSON object."""


def reviewer_node(state: PipelineState, model: str) -> tuple[dict, Usage]:
    artifact_count = len(state.get("artifacts", []))
    tests_passed = state.get("test_results", {}).get("passed", False)
    test_summary = state.get("test_results", {}).get("summary", "no tests run")

    user_msg = (
        f"Artifacts produced: {artifact_count}\n"
        f"Tests passed: {tests_passed}\n"
        f"Test summary: {test_summary}\n"
        f"Plan: {json.dumps(state.get('plan', {}), indent=2)}"
    )

    text, usage = call_model(model, inject_skills(_SYSTEM, state), user_msg, **model_kwargs_from_state(state))

    try:
        result = json.loads(text)
        approved = result.get("approved", False)
    except json.JSONDecodeError:
        approved = False
        result = {"approved": False, "notes": text}

    return {"phase": "review" if approved else "dev"}, usage
