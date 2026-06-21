"""Report node — writes the final pipeline report on success."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from src.state import PipelineState


def report_node(state: PipelineState, db=None) -> dict:
    """Terminal node: produce the final report on successful completion."""
    budget = state.get("budget", {})
    cost_used = budget.get("cost_used_usd", 0.0)
    cost_limit = budget.get("cost_limit_usd", 1.0)

    findings_by_severity: dict[str, list] = {}
    for f in state.get("findings", []):
        findings_by_severity.setdefault(f["severity"], []).append(f)

    report = {
        "status": "complete",
        "run_id": state.get("run_id"),
        "feature_request": state.get("feature_request"),
        "verdict": state.get("verdict", "clean"),
        "phase_completed": state.get("phase"),
        "plan_summary": state.get("plan", {}).get("summary", "N/A"),
        "tech_stack": state.get("tech_stack", []),
        "artifacts": [{"path": a["path"], "kind": a["kind"]} for a in state.get("artifacts", [])],
        "test_results": state.get("test_results", {}),
        "findings_summary": {sev: len(items) for sev, items in findings_by_severity.items()},
        "findings": state.get("findings", []),
        "budget_summary": {
            "tokens_used": budget.get("tokens_used", 0),
            "tokens_limit": budget.get("tokens_limit", 0),
            "cost_used_usd": cost_used,
            "cost_limit_usd": cost_limit,
            "cost_utilization_pct": round((cost_used / cost_limit) * 100, 1) if cost_limit else 0,
            "steps_taken": budget.get("steps_taken", 0),
            "steps_limit": budget.get("steps_limit", 0),
        },
        "audit_entries": len(state.get("audit", [])),
        "timestamp": datetime.now(UTC).isoformat(),
    }

    print(f"\n{'=' * 60}")
    print("PIPELINE COMPLETE")
    print(json.dumps(report, indent=2))
    print("=" * 60)

    # RAG use case 5: persist this run's plan + lessons for future runs to learn from.
    if db is not None:
        from src.rag.recipes import persist_run_memory

        persist_run_memory(state, db)

    return {"phase": "done"}
