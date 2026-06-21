"""Review Supervisor — routes codebase to specialists and aggregates findings."""
from __future__ import annotations

import json
from typing import Literal

from src.agents.base import Usage, call_model, inject_skills
from src.state import Finding, PipelineState

_SYSTEM = """You are the Review Supervisor in a software review pipeline.
Aggregate the findings from all review specialists and produce a final verdict.

Respond with a JSON object:
{
  "verdict": "clean" | "minor" | "critical",
  "summary": "brief overall assessment",
  "action_required": "what needs to happen next (if anything)"
}

Use "critical" if any finding has severity "critical" or "major".
Use "minor" if there are only minor/info findings.
Use "clean" if no significant findings.

Respond ONLY with this JSON object."""


def review_supervisor_node(state: PipelineState, model: str) -> tuple[dict, Usage]:
    findings = state.get("findings", [])
    findings_text = json.dumps(findings, indent=2) if findings else "[]"

    user_msg = (
        f"Feature: {state['feature_request']}\n\n"
        f"Review findings from all specialists:\n{findings_text}"
    )

    text, usage = call_model(model, inject_skills(_SYSTEM, state), user_msg)

    try:
        result = json.loads(text)
        verdict: Literal["clean", "minor", "critical"] = result.get("verdict", "clean")
    except json.JSONDecodeError:
        verdict = "critical"
        result = {"verdict": "critical", "summary": text}

    return {"verdict": verdict}, usage
