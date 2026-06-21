"""WebSocket handler — streams pipeline events to the browser in real time."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

# Per-run event queues: run_id → asyncio.Queue[dict]
_queues: dict[str, asyncio.Queue] = {}

# Reference to the main event loop — set once at app startup so the pipeline
# thread can schedule puts without blocking the loop.
_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def create_queue(run_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=1000)
    _queues[run_id] = q
    return q


def get_queue(run_id: str) -> asyncio.Queue | None:
    return _queues.get(run_id)


def publish(run_id: str, event: dict) -> None:
    """Thread-safe publish from the pipeline worker thread to the WebSocket queue.

    Uses call_soon_threadsafe so the put runs on the main event loop — asyncio
    Queue is not safe to call from a foreign thread directly.
    """
    q = _queues.get(run_id)
    loop = _main_loop
    if q is None or loop is None:
        return

    def _put() -> None:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass  # drop rather than block the pipeline thread

    loop.call_soon_threadsafe(_put)


def cleanup_queue(run_id: str) -> None:
    _queues.pop(run_id, None)


async def pipeline_ws(websocket: WebSocket, run_id: str) -> None:
    """WebSocket endpoint at /ws/runs/{run_id}.

    Validates the auth cookie then verifies the run belongs to the caller
    before relaying events from the run's queue.
    """
    from ui.backend.auth import COOKIE_NAME, decode_token
    from ui.backend.dependencies import get_db
    from fastapi import HTTPException

    # ── Authentication ────────────────────────────────────────────────────────
    token = websocket.cookies.get(COOKIE_NAME)
    if not token:
        await websocket.close(code=4001)
        return
    try:
        user = decode_token(token)
    except HTTPException:
        await websocket.close(code=4001)
        return

    # ── Authorization: verify this run belongs to the authenticated user ──────
    db = get_db()
    if not db.get_run(run_id, user.user_id):
        await websocket.close(code=4003)
        return

    await websocket.accept()

    q = get_queue(run_id)
    if q is None:
        await websocket.send_json({"type": "error", "message": "run not found"})
        await websocket.close()
        return

    try:
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=30.0)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
                continue

            await websocket.send_json(event)

            if event.get("type") in ("done", "halt", "error"):
                break
    except WebSocketDisconnect:
        pass
    finally:
        cleanup_queue(run_id)
