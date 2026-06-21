"""Security Auditor — vulnerabilities, secrets, injection, dependency CVEs."""

from __future__ import annotations

import json

from src.agents.base import Usage, call_model, inject_skills, model_kwargs_from_state
from src.agents.outputs import ReviewFinding
from src.guardrails import parse_llm_json_list
from src.state import Finding, PipelineState

_SYSTEM = """You are a Security Auditor agent reviewing source code.
Check for:
- SQL injection, command injection, XSS vulnerabilities
- Hardcoded secrets or credentials
- Insecure dependencies
- Missing input validation
- Improper authentication/authorization
- OWASP Top 10 issues

Respond with a JSON array of findings:
[{
  "severity": "critical" | "major" | "minor" | "info",
  "message": "description of the issue",
  "location": "file:line or component name"
}]

Return [] if no issues found. Respond ONLY with the JSON array."""


def security_node(state: PipelineState, model: str, db=None) -> tuple[dict, Usage]:
    artifact_paths = [a["path"] for a in state.get("artifacts", [])]
    user_msg = (
        f"Feature: {state['feature_request']}\n\n"
        f"Review these artifacts for security issues:\n{json.dumps(artifact_paths)}"
    )

    # RAG use case 4: recall known CVEs + codebase map for this run.
    if db is not None:
        from src.rag.recipes import retrieve_security_context

        sec_ctx = retrieve_security_context(
            state["feature_request"], db, state.get("run_id", ""), k=5
        )
        if sec_ctx:
            user_msg += f"\n\n{sec_ctx}"

    text, usage = call_model(
        model, inject_skills(_SYSTEM, state), user_msg, **model_kwargs_from_state(state)
    )

    parsed = parse_llm_json_list(text, ReviewFinding, context="security")
    findings: list[Finding] = [
        Finding(agent="security", severity=f.severity, message=f.message, location=f.location)
        for f in parsed
    ]
    return {"findings": findings}, usage
