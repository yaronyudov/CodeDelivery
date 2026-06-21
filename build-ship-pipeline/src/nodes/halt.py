"""Halt node — graceful stop that writes a partial report."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from src.state import PipelineState


def halt_node(state: PipelineState) -> dict:
    """Terminal node: write a partial report when budget is exceeded or halted."""
    reason = state.get("halt_reason", "unknown")
    budget = state.get("budget", {})

    report = {
        "status": "halted",
        "run_id": state.get("run_id"),
        "halt_reason": reason,
        "phase_at_halt": state.get("phase"),
        "artifacts_produced": len(state.get("artifacts", [])),
        "findings": state.get("findings", []),
        "budget_summary": {
            "tokens_used": budget.get("tokens_used", 0),
            "tokens_limit": budget.get("tokens_limit", 0),
            "cost_used_usd": budget.get("cost_used_usd", 0.0),
            "cost_limit_usd": budget.get("cost_limit_usd", 0.0),
            "steps_taken": budget.get("steps_taken", 0),
            "steps_limit": budget.get("steps_limit", 0),
        },
        "audit_entries": len(state.get("audit", [])),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    print(f"\n{'='*60}")
    print("PIPELINE HALTED")
    print(f"Reason: {reason}")
    print(json.dumps(report, indent=2))
    print("=" * 60)

    return {"phase": "halted"}
