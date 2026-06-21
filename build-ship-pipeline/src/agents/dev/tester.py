"""Tester agent — generates and runs unit, integration, and E2E tests."""
from __future__ import annotations

import json
import uuid

from src.agents.base import Usage, call_model
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
        f"Build plan:\n{plan_text}\n\n"
        f"Artifact paths:\n{json.dumps(artifact_paths, indent=2)}"
    )

    text, usage = call_model(model, _SYSTEM, user_msg, max_tokens=4096)

    artifacts: list[Artifact] = []
    test_results: dict = {"passed": False, "summary": "", "failures": []}

    try:
        data = json.loads(text)
        for f in data.get("files", []):
            ref = str(uuid.uuid4())
            if db is not None:
                ref = db.save_artifact(
                    run_id=state["run_id"],
                    kind="test",
                    path=f["path"],
                    version=1,
                    content=f["content"],
                )
            artifacts.append(
                Artifact(
                    path=f["path"],
                    kind="test",
                    content_ref=ref,
                    version=1,
                )
            )
        test_results = data.get("results", test_results)
    except (json.JSONDecodeError, KeyError):
        pass

    return {"artifacts": artifacts, "test_results": test_results}, usage
