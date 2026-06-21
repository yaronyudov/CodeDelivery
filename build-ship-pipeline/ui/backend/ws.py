"""WebSocket handler — streams pipeline events to the browser in real time."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

# Per-run event queues: run_id → asyncio.Queue[dict]
_queues: dict[str, asyncio.Queue] = {}


def create_queue(run_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=1000)
    _queues[run_id] = q
    return q


def get_queue(run_id: str) -> asyncio.Queue | None:
    return _queues.get(run_id)


def publish(run_id: str, event: dict) -> None:
    """Thread-safe publish from the pipeline thread to the WebSocket queue."""
    q = _queues.get(run_id)
    if q:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass  # drop rather than block the pipeline


def cleanup_queue(run_id: str) -> None:
    _queues.pop(run_id, None)


async def pipeline_ws(websocket: WebSocket, run_id: str) -> None:
    """WebSocket endpoint at /ws/runs/{run_id}.

    Validates the auth cookie then relays events from the run's queue.
    """
    from ui.backend.auth import COOKIE_NAME, decode_token
    from fastapi import HTTPException

    # Auth check on the WebSocket handshake
    token = websocket.cookies.get(COOKIE_NAME)
    if not token:
        await websocket.close(code=4001)
        return
    try:
        decode_token(token)
    except HTTPException:
        await websocket.close(code=4001)
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
                # Send ping to keep connection alive
                await websocket.send_json({"type": "ping"})
                continue

            await websocket.send_json(event)

            if event.get("type") in ("done", "halt", "error"):
                break
    except WebSocketDisconnect:
        pass
    finally:
        cleanup_queue(run_id)
