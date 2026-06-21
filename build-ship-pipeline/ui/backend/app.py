"""FastAPI application factory."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from ui.backend import auth, runs
from ui.backend.ws import pipeline_ws

_FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

limiter = Limiter(key_func=get_remote_address)


def create_app() -> FastAPI:
    app = FastAPI(title="Build & Ship Pipeline UI", docs_url=None, redoc_url=None)

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if os.getenv("DEV_MODE") else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix="/api/auth")
    app.include_router(runs.router, prefix="/api/runs")
    app.add_api_websocket_route("/ws/runs/{run_id}", pipeline_ws)

    # Serve React SPA from dist/ (falls back to index.html for client-side routing)
    if _FRONTEND_DIST.exists():
        app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str, request: Request):
            index = _FRONTEND_DIST / "index.html"
            if index.exists():
                return FileResponse(index)
            return {"detail": "Frontend not built. Run: cd ui/frontend && npm run build"}

    return app


app = create_app()
