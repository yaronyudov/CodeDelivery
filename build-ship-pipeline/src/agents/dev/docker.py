"""Docker Compose agent — generates docker-compose.yml and service configs."""
from __future__ import annotations

import json
import uuid

from src.agents.base import Usage, call_model, inject_skills, model_kwargs_from_state
from src.state import Artifact, PipelineState

_SYSTEM = """You are the Docker Compose agent in a software build pipeline.
Given a build plan and tech stack, produce a complete docker-compose.yml
plus service configuration files.

IMPORTANT: Always include the monitoring stack:
- prometheus (port 9090)
- grafana (port 3000)
- loki (port 3100)
- tempo (port 3200)
- otel-collector (ports 4317, 4318)

Respond with a JSON array of file objects:
[{"path": "docker-compose.yml", "content": "...", "kind": "compose"}, ...]

The compose file must use version "3.9" and define all required services,
networks, and volumes. Respond ONLY with the JSON array."""


def docker_node(state: PipelineState, model: str, db=None) -> tuple[dict, Usage]:
    plan_text = json.dumps(state["plan"], indent=2)
    stack_text = ", ".join(state.get("tech_stack", []))
    user_msg = f"Build plan:\n{plan_text}\n\nTech stack: {stack_text}"

    text, usage = call_model(model, inject_skills(_SYSTEM, state), user_msg, max_tokens=4096, **model_kwargs_from_state(state))

    artifacts: list[Artifact] = []
    try:
        files = json.loads(text)
        for f in files:
            ref = str(uuid.uuid4())
            if db is not None:
                ref = db.save_artifact(
                    run_id=state["run_id"],
                    kind=f.get("kind", "compose"),
                    path=f["path"],
                    version=1,
                    content=f["content"],
                )
            artifacts.append(
                Artifact(
                    path=f["path"],
                    kind=f.get("kind", "compose"),
                    content_ref=ref,
                    version=1,
                )
            )
    except (json.JSONDecodeError, KeyError):
        pass

    return {"artifacts": artifacts}, usage
