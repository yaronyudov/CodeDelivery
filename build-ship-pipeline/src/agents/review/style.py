"""Style Checker — conventions, readability, lint/format compliance."""
from __future__ import annotations

import json

from src.agents.base import Usage, call_model, inject_skills, model_kwargs_from_state
from src.agents.outputs import ReviewFinding
from src.guardrails import parse_llm_json_list
from src.state import Finding, PipelineState

_SYSTEM = """You are a Style Checker agent reviewing source code.
Check for:
- PEP 8 / language-specific style violations
- Inconsistent naming conventions
- Missing type annotations
- Overly complex functions (high cyclomatic complexity)
- Dead code, unused imports
- Poor readability or misleading names

Respond with a JSON array of findings:
[{
  "severity": "minor" | "info",
  "message": "description of the style issue",
  "location": "file:line or component name"
}]

Return [] if no issues found. Respond ONLY with the JSON array."""


def style_node(state: PipelineState, model: str) -> tuple[dict, Usage]:
    artifact_paths = [a["path"] for a in state.get("artifacts", []) if a["kind"] == "code"]
    user_msg = (
        f"Review these source files for style issues:\n{json.dumps(artifact_paths)}"
    )

    text, usage = call_model(model, inject_skills(_SYSTEM, state), user_msg, **model_kwargs_from_state(state))

    parsed = parse_llm_json_list(text, ReviewFinding, context="style")
    findings: list[Finding] = [
        Finding(agent="style", severity=f.severity, message=f.message, location=f.location)
        for f in parsed
    ]
    return {"findings": findings}, usage
