"""Debugger agent — diagnoses test failures and routes fixes."""
from __future__ import annotations

import json

from src.agents.base import Usage, call_model, inject_skills
from src.state import PipelineState

_SYSTEM = """You are the Debugger agent in a software build pipeline.
Given test failures, diagnose root causes and produce a fix plan.

Respond with a JSON object:
{
  "diagnosis": "brief description of what went wrong",
  "fix_targets": ["src/foo.py", "src/bar.py"],
  "fix_instructions": "Detailed instructions for the Coder agent to fix",
  "escalate_to_planner": false
}

Set escalate_to_planner=true only if the failures indicate a fundamental
architectural problem that requires re-planning.

Respond ONLY with this JSON object."""


def debugger_node(state: PipelineState, model: str) -> tuple[dict, Usage]:
    failures = state.get("test_results", {}).get("failures", [])
    attempts = state.get("debug_attempts", 0)

    user_msg = (
        f"Test failures (attempt {attempts + 1}):\n{json.dumps(failures, indent=2)}\n\n"
        f"Plan summary: {state.get('plan', {}).get('summary', 'N/A')}"
    )

    text, usage = call_model(model, inject_skills(_SYSTEM, state), user_msg)

    try:
        diagnosis = json.loads(text)
    except json.JSONDecodeError:
        diagnosis = {
            "diagnosis": text,
            "fix_targets": [],
            "fix_instructions": text,
            "escalate_to_planner": False,
        }

    new_plan = dict(state.get("plan", {}))
    if diagnosis.get("fix_instructions"):
        new_plan["debug_fix_instructions"] = diagnosis["fix_instructions"]

    return {
        "plan": new_plan,
        "debug_attempts": attempts + 1,
    }, usage
