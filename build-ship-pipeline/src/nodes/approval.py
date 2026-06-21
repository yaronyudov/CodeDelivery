"""Human approval gate — pauses the pipeline between planner and coder.

Uses a process-level asyncio.Event per run_id so the WebSocket handler
can signal approval or rejection from outside the graph.
"""
from __future__ import annotations

import asyncio
from typing import Any

# Process-level registry: run_id → {"event": asyncio.Event, "approved": bool}
_gates: dict[str, dict[str, Any]] = {}


def register_run(run_id: str) -> None:
    """Call once when a run starts so the gate exists before the node runs."""
    _gates[run_id] = {"event": asyncio.Event(), "approved": False}


def signal_approval(run_id: str, approved: bool) -> None:
    """Called by the HTTP /approve or /reject endpoint."""
    gate = _gates.get(run_id)
    if gate:
        gate["approved"] = approved
        gate["event"].set()


def cleanup_run(run_id: str) -> None:
    _gates.pop(run_id, None)


def approval_gate_node(state: dict) -> dict:
    """LangGraph node.  Zero cost — no LLM call.

    If require_approval is False, passes straight through.
    Otherwise blocks until signal_approval() is called from the HTTP layer.
    Runs synchronously inside the LangGraph thread pool.
    """
    if not state.get("require_approval", False):
        return {}

    run_id = state["run_id"]
    gate = _gates.get(run_id)

    if gate is None:
        # Gate not registered — treat as approved to avoid deadlock
        return {"approval_status": "approved"}

    # Mark pending and wait (runs in a thread; asyncio event is thread-safe via run_until_complete)
    loop = _get_or_create_loop()
    future = asyncio.run_coroutine_threadsafe(gate["event"].wait(), loop)
    future.result(timeout=3600)  # 1-hour hard timeout

    approved = gate.get("approved", False)
    cleanup_run(run_id)

    if not approved:
        return {
            "phase": "halted",
            "halt_reason": "rejected by human reviewer",
            "approval_status": "rejected",
        }

    return {"approval_status": "approved"}


def _get_or_create_loop() -> asyncio.AbstractEventLoop:
    """Return the running event loop, or create a background one if none exists."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return loop
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop
