"""Test Coverage Inspector — coverage gaps, missing edge cases, flaky tests."""
from __future__ import annotations

from src.agents.base import Usage, call_model, inject_skills, model_kwargs_from_state
from src.agents.outputs import ReviewFinding
from src.guardrails import parse_llm_json_list
from src.state import Finding, PipelineState

_SYSTEM = """You are a Test Coverage Inspector agent reviewing test suites.
Check for:
- Untested code paths or modules
- Missing edge case tests (empty inputs, boundary values, error paths)
- Tests with no assertions
- Potentially flaky tests (time-dependent, ordering-dependent)
- Missing integration or E2E coverage for critical flows

Respond with a JSON array of findings:
[{
  "severity": "major" | "minor" | "info",
  "message": "description of the coverage gap",
  "location": "file or module name"
}]

Return [] if coverage looks good. Respond ONLY with the JSON array."""


def coverage_node(state: PipelineState, model: str) -> tuple[dict, Usage]:
    test_paths = [a["path"] for a in state.get("artifacts", []) if a["kind"] == "test"]
    code_paths = [a["path"] for a in state.get("artifacts", []) if a["kind"] == "code"]

    user_msg = (
        f"Code files:\n{json.dumps(code_paths)}\n\n"
        f"Test files:\n{json.dumps(test_paths)}"
    )

    text, usage = call_model(model, inject_skills(_SYSTEM, state), user_msg, **model_kwargs_from_state(state))

    parsed = parse_llm_json_list(text, ReviewFinding, context="coverage")
    findings: list[Finding] = [
        Finding(agent="coverage", severity=f.severity, message=f.message, location=f.location)
        for f in parsed
    ]
    return {"findings": findings}, usage
