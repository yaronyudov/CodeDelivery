"""Tester agent — generates and runs unit, integration, and E2E tests."""

from __future__ import annotations

import json
import uuid

from src.agents.base import Usage, call_model, inject_skills, model_kwargs_from_state
from src.agents.outputs import TesterOutput
from src.guardrails import parse_llm_json
from src.state import Artifact, PipelineState

_SYSTEM = """You are the Tester agent in a software build pipeline.
Given the build plan and artifact list, produce pytest test files AND
a test results report.

Respond with a JSON object:
{
  "files": [{"path": "tests/test_foo.py", "content": "...", "kind": "test"}],
  "results": {
    "passed": true,
    "summary": "5 passed, 0 failed",
    "failures": []
  }
}

The test files should cover:
- Unit tests for each module
- Integration tests for API endpoints
- E2E smoke tests

Respond ONLY with this JSON object."""


def tester_node(state: PipelineState, model: str, db=None) -> tuple[dict, Usage]:
    plan_text = json.dumps(state["plan"], indent=2)
    artifact_paths = [a["path"] for a in state.get("artifacts", [])]
    user_msg = (
        f"Build plan:\n{plan_text}\n\nArtifact paths:\n{json.dumps(artifact_paths, indent=2)}"
    )

    text, usage = call_model(
        model,
        inject_skills(_SYSTEM, state),
        user_msg,
        max_tokens=4096,
        **model_kwargs_from_state(state),
    )

    parsed = parse_llm_json(text, TesterOutput, context="tester")
    artifacts: list[Artifact] = []
    for f in parsed.files:
        ref = str(uuid.uuid4())
        if db is not None:
            ref = db.save_artifact(
                run_id=state["run_id"],
                kind="test",
                path=f.path,
                version=1,
                content=f.content,
            )
        artifacts.append(Artifact(path=f.path, kind="test", content_ref=ref, version=1))

    test_results = parsed.results.model_dump()
    return {"artifacts": artifacts, "test_results": test_results}, usage
