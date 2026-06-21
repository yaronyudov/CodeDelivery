"""Coder agent — writes application code from the plan."""
from __future__ import annotations

import json
import uuid

from src.agents.base import Usage, call_model, inject_skills, model_kwargs_from_state
from src.state import Artifact, PipelineState

_SYSTEM = """You are the Coder agent in a software build pipeline.
Given a build plan, produce the application source files.

Respond with a JSON array of file objects:
[{"path": "src/main.py", "content": "...", "kind": "code"}, ...]

Include all files needed to implement the plan. Write production-quality code.
Respond ONLY with the JSON array."""


def coder_node(state: PipelineState, model: str, db=None) -> tuple[dict, Usage]:
    plan_text = json.dumps(state["plan"], indent=2)
    debug_context = ""
    if state.get("debug_attempts", 0) > 0:
        debug_context = f"\n\nPrevious test failures occurred. debug_attempts={state['debug_attempts']}. Fix the issues."

    user_msg = f"Build plan:\n{plan_text}{debug_context}"
    text, usage = call_model(model, inject_skills(_SYSTEM, state), user_msg, max_tokens=8192, **model_kwargs_from_state(state))

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
                    kind=f.get("kind", "code"),
                    content_ref=ref,
                    version=1,
                )
            )
    except (json.JSONDecodeError, KeyError):
        pass

    return {"artifacts": artifacts}, usage
