"""Human approval gate — pauses the pipeline between planner and coder.

Uses a process-level asyncio.Event per run_id so the WebSocket handler
can signal approval or rejection from outside the graph.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Process-level registry: run_id → {"event": asyncio.Event, "approved": bool}
_gates: dict[str, dict[str, Any]] = {}

# Reference to the main event loop, set at app startup.
# Required so the approval gate (running in a worker thread) can schedule a
# wait on the correct loop via run_coroutine_threadsafe.
_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def register_run(run_id: str) -> None:
    """Call once when a run starts so the gate exists before the node runs."""
    _gates[run_id] = {"event": asyncio.Event(), "approved": False}


def signal_approval(run_id: str, approved: bool) -> None:
    """Called from the HTTP /approve or /reject endpoint (main event loop)."""
    gate = _gates.get(run_id)
    if gate:
        gate["approved"] = approved
        gate["event"].set()


def cleanup_run(run_id: str) -> None:
    _gates.pop(run_id, None)


def approval_gate_node(state: dict) -> dict:
    """LangGraph node. Zero cost — no LLM call.

    If require_approval is False, passes straight through.
    Otherwise blocks the worker thread until signal_approval() is called
    from the main event loop (via the HTTP approve/reject endpoint).
    """
    if not state.get("require_approval", False):
        return {}

    run_id = state["run_id"]
    gate = _gates.get(run_id)

    if gate is None:
        # Gate not registered — treat as approved to avoid deadlock
        return {"approval_status": "approved"}

    loop = _main_loop
    if loop is None:
        # Running without the web server (tests / CLI) — skip gate
        logger.warning("approval_gate_node: no main loop set, treating as approved")
        return {"approval_status": "approved"}

    # Block the worker thread (not the event loop) until the browser approves/rejects.
    # run_coroutine_threadsafe schedules gate["event"].wait() on the main loop;
    # .result() blocks this thread until the coroutine completes.
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
