"""CLI entrypoint: python -m src.main 'Build a REST API for todo items'"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from src.graph import build_graph  # noqa: E402
from src.observability import setup_tracing  # noqa: E402
from src.state import initial_state  # noqa: E402


def main(feature_request: str) -> None:
    setup_tracing()

    run_id = str(uuid.uuid4())
    state = initial_state(run_id=run_id, feature_request=feature_request)

    print(f"Starting pipeline run {run_id}")
    print(f"Feature: {feature_request}\n")

    app = build_graph()
    config = {"configurable": {"thread_id": run_id}}

    for step in app.stream(state, config=config):
        node, output = next(iter(step.items()))
        phase = output.get("phase", "?")
        budget = output.get("budget", {})
        steps = budget.get("steps_taken", "?")
        cost = budget.get("cost_used_usd", 0.0)
        print(f"  [{steps:>3}] {node:<25} phase={phase}  cost=${cost:.4f}")

    print("\nDone.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.main 'Your feature request here'")
        sys.exit(1)
    main(sys.argv[1])
