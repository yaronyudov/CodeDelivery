"""Performance Analyst — hotpaths, N+1 queries, allocation, latency budgets."""
from __future__ import annotations

import json

from src.agents.base import Usage, call_model, inject_skills
from src.state import Finding, PipelineState

_SYSTEM = """You are a Performance Analyst agent reviewing source code.
Check for:
- N+1 database query patterns
- Synchronous blocking operations in async contexts
- Missing database indexes
- Unbounded loops or recursion
- Memory leaks and large allocations
- Missing caching opportunities
- Latency-sensitive paths without timeouts

Respond with a JSON array of findings:
[{
  "severity": "critical" | "major" | "minor" | "info",
  "message": "description of the performance issue",
  "location": "file:line or component name"
}]

Return [] if no issues found. Respond ONLY with the JSON array."""


def perf_node(state: PipelineState, model: str) -> tuple[dict, Usage]:
    artifact_paths = [a["path"] for a in state.get("artifacts", [])]
    user_msg = (
        f"Feature: {state['feature_request']}\n\n"
        f"Review these artifacts for performance issues:\n{json.dumps(artifact_paths)}"
    )

    text, usage = call_model(model, inject_skills(_SYSTEM, state), user_msg)

    findings: list[Finding] = []
    try:
        raw = json.loads(text)
        findings = [
            Finding(
                agent="perf",
                severity=f.get("severity", "info"),
                message=f.get("message", ""),
                location=f.get("location", "unknown"),
            )
            for f in raw
        ]
    except (json.JSONDecodeError, KeyError):
        pass

    return {"findings": findings}, usage
