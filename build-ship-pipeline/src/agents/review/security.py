"""Security Auditor — vulnerabilities, secrets, injection, dependency CVEs."""
from __future__ import annotations

import json

from src.agents.base import Usage, call_model, inject_skills, model_kwargs_from_state
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


def security_node(state: PipelineState, model: str) -> tuple[dict, Usage]:
    artifact_paths = [a["path"] for a in state.get("artifacts", [])]
    user_msg = (
        f"Feature: {state['feature_request']}\n\n"
        f"Review these artifacts for security issues:\n{json.dumps(artifact_paths)}"
    )

    text, usage = call_model(model, inject_skills(_SYSTEM, state), user_msg, **model_kwargs_from_state(state))

    findings: list[Finding] = []
    try:
        raw = json.loads(text)
        findings = [
            Finding(
                agent="security",
                severity=f.get("severity", "info"),
                message=f.get("message", ""),
                location=f.get("location", "unknown"),
            )
            for f in raw
        ]
    except (json.JSONDecodeError, KeyError):
        pass

    return {"findings": findings}, usage
