"""Observability agent — instruments generated code with OTel, writes Grafana dashboards."""
from __future__ import annotations

import json
import uuid

from src.agents.base import Usage, call_model, inject_skills
from src.state import Artifact, PipelineState

_SYSTEM = """You are the Observability agent in a software build pipeline.
Your job is to instrument the generated application with OpenTelemetry and
create Grafana dashboards and alert rules.

Given the build plan and existing artifacts, produce:
1. Patched source files with OTel SDK initialization and spans/metrics
2. Grafana dashboard JSON files
3. Prometheus alert rule files

Respond with a JSON array of file objects:
[{"path": "src/telemetry.py", "content": "...", "kind": "code"}, ...]

For dashboards use kind "dashboard". Respond ONLY with the JSON array."""


def observability_node(state: PipelineState, model: str, db=None) -> tuple[dict, Usage]:
    plan_text = json.dumps(state["plan"], indent=2)
    artifact_paths = [a["path"] for a in state.get("artifacts", [])]
    user_msg = (
        f"Build plan:\n{plan_text}\n\n"
        f"Existing artifact paths:\n{json.dumps(artifact_paths, indent=2)}"
    )

    text, usage = call_model(model, inject_skills(_SYSTEM, state), user_msg, max_tokens=4096)

    artifacts: list[Artifact] = []
    try:
        files = json.loads(text)
        for f in files:
            ref = str(uuid.uuid4())
            if db is not None:
                ref = db.save_artifact(
                    run_id=state["run_id"],
                    kind=f.get("kind", "code"),
                    path=f["path"],
                    version=1,
                    content=f["content"],
                )
            artifacts.append(
                Artifact(
                    path=f["path"],
                    kind=f.get("kind", "dashboard"),
                    content_ref=ref,
                    version=1,
                )
            )
    except (json.JSONDecodeError, KeyError):
        pass

    return {"artifacts": artifacts}, usage
