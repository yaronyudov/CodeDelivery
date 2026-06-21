"""Run management endpoints: start, stop, approve, history."""
from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.nodes.approval import register_run, signal_approval
from src.state import initial_state
from ui.backend.dependencies import get_current_user, get_db
from ui.backend.models import ApproveRequest, RunSummary, StartRunRequest, TokenData
from ui.backend.ws import create_queue, publish

logger = logging.getLogger(__name__)

router = APIRouter(tags=["runs"])

# Per-run stop flags: run_id → bool  (GIL makes dict access thread-safe)
_stop_flags: dict[str, bool] = {}


def _is_stopped(run_id: str) -> bool:
    return _stop_flags.get(run_id, False)


@router.get("", response_model=list[RunSummary])
async def list_runs(
    request: Request,
    user: TokenData = Depends(get_current_user),
):
    db = get_db()
    rows = db.list_runs(user.user_id)
    return [
        RunSummary(
            run_id=r["run_id"],
            feature_request=r["feature_request"],
            status=r["status"],
            verdict=r.get("verdict"),
            require_approval=r["require_approval"],
            created_at=str(r["created_at"]),
            finished_at=str(r["finished_at"]) if r.get("finished_at") else None,
        )
        for r in rows
    ]


@router.get("/{run_id}", response_model=RunSummary)
async def get_run(
    run_id: str,
    user: TokenData = Depends(get_current_user),
):
    db = get_db()
    row = db.get_run(run_id, user.user_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return RunSummary(
        run_id=row["run_id"],
        feature_request=row["feature_request"],
        status=row["status"],
        verdict=row.get("verdict"),
        require_approval=row["require_approval"],
        created_at=str(row["created_at"]),
        finished_at=str(row["finished_at"]) if row.get("finished_at") else None,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def start_run(
    body: StartRunRequest,
    user: TokenData = Depends(get_current_user),
):
    run_id = str(uuid.uuid4())
    db = get_db()

    model_cfg = {
        "provider": body.model_config_.provider,
        "model": body.model_config_.model,
        "api_base": body.model_config_.api_base,
        # API key held in memory only — not persisted to DB
        "api_key": body.model_config_.api_key,
    }

    # Strip API key before writing to the database
    model_cfg_stored = {k: v for k, v in model_cfg.items() if k != "api_key"}

    db.create_run(
        run_id=run_id,
        user_id=user.user_id,
        feature_request=body.feature_request,
        model_config=model_cfg_stored,
        require_approval=body.require_approval,
    )

    # Set up approval gate and WebSocket queue before launching the thread
    if body.require_approval:
        register_run(run_id)
    create_queue(run_id)

    # Run the blocking pipeline in a worker thread so the event loop stays free
    asyncio.create_task(
        _run_pipeline(
            run_id=run_id,
            feature_request=body.feature_request,
            model_config=model_cfg,   # full config with api_key for the run
            require_approval=body.require_approval,
        )
    )

    return {"run_id": run_id}


@router.post("/{run_id}/stop")
async def stop_run(
    run_id: str,
    user: TokenData = Depends(get_current_user),
):
    db = get_db()
    if not db.get_run(run_id, user.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    _stop_flags[run_id] = True
    return {"ok": True}


@router.post("/{run_id}/approve")
async def approve_run(
    run_id: str,
    body: ApproveRequest,
    user: TokenData = Depends(get_current_user),
):
    db = get_db()
    if not db.get_run(run_id, user.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    signal_approval(run_id, body.approved)
    return {"ok": True}


@router.post("/{run_id}/reject")
async def reject_run(
    run_id: str,
    user: TokenData = Depends(get_current_user),
):
    db = get_db()
    if not db.get_run(run_id, user.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    signal_approval(run_id, approved=False)
    return {"ok": True}


# ── Pipeline execution ────────────────────────────────────────────────────────

async def _run_pipeline(
    run_id: str,
    feature_request: str,
    model_config: dict,
    require_approval: bool,
) -> None:
    """Async wrapper — offloads the blocking pipeline to a worker thread."""
    await asyncio.to_thread(
        _run_pipeline_sync, run_id, feature_request, model_config, require_approval
    )


def _run_pipeline_sync(
    run_id: str,
    feature_request: str,
    model_config: dict,
    require_approval: bool,
) -> None:
    """Synchronous pipeline runner — safe to call from a worker thread.

    Publishes typed events to the run's WebSocket queue as the graph streams.
    All publish() calls are thread-safe (they schedule onto the main event loop).
    """
    from src.graph import build_graph

    db = get_db()
    state = initial_state(
        run_id=run_id,
        feature_request=feature_request,
        require_approval=require_approval,
        model_config=model_config,
    )

    app = build_graph(db)
    config = {"configurable": {"thread_id": run_id}}

    verdict = None
    final_status = "done"

    try:
        for step_output in app.stream(state, config=config):
            node_name, node_result = next(iter(step_output.items()))

            # Check stop flag between nodes
            if _stop_flags.get(run_id):
                final_status = "stopped"
                publish(run_id, {"type": "halt", "reason": "stopped by user"})
                break

            phase = node_result.get("phase", "dev")
            budget = node_result.get("budget", {})

            # Emit step event
            audit_entries = node_result.get("audit", [])
            if audit_entries:
                entry = audit_entries[-1]
                publish(run_id, {
                    "type": "step",
                    "agent": entry.get("agent", node_name),
                    "phase": phase,
                    "step": entry.get("step", budget.get("steps_taken", 0)),
                    "tokens": entry.get("tokens", 0),
                    "cost_usd": entry.get("cost_usd", 0.0),
                    "latency_s": entry.get("latency_s", 0.0),
                })

            # Emit budget snapshot
            if budget:
                publish(run_id, {
                    "type": "budget",
                    "tokens_used": budget.get("tokens_used", 0),
                    "cost_used_usd": budget.get("cost_used_usd", 0.0),
                    "steps_taken": budget.get("steps_taken", 0),
                })

            # Emit new artifacts
            for artifact in node_result.get("artifacts", []):
                publish(run_id, {"type": "artifact", "path": artifact["path"], "kind": artifact["kind"]})

            # Emit new findings
            for finding in node_result.get("findings", []):
                publish(run_id, {
                    "type": "finding",
                    "severity": finding["severity"],
                    "agent": finding["agent"],
                    "message": finding["message"],
                    "location": finding["location"],
                })

            # Emit approval_required
            if node_name == "approval_gate" and node_result.get("approval_status") == "pending":
                publish(run_id, {"type": "approval_required", "plan": state.get("plan", {})})

            if phase == "halted":
                final_status = "halted"
                publish(run_id, {"type": "halt", "reason": node_result.get("halt_reason", "unknown")})
                break

            if phase == "done":
                verdict = node_result.get("verdict")

    except Exception:
        logger.exception("Pipeline %s failed", run_id)
        final_status = "halted"
        publish(run_id, {"type": "error", "message": "Pipeline encountered an error. Check server logs."})

    finally:
        _stop_flags.pop(run_id, None)
        db.finish_run(run_id, status=final_status, verdict=verdict)
        if final_status == "done":
            publish(run_id, {
                "type": "done",
                "verdict": verdict or "clean",
                "cost_total": 0.0,
            })
