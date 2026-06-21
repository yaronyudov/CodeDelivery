"""HTTP middleware: correlation IDs and structured access logging."""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.observability.logger import get_logger

_log = get_logger("http.access")

_SKIP_LOG = {"/health", "/favicon.ico"}


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attaches a request-scoped correlation ID to every request.

    Reads X-Request-ID from the incoming headers (or generates a UUID4).
    Echoes it back in the response and makes it available via
    request.state.correlation_id so downstream code can log it.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        cid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.correlation_id = cid

        t0 = time.perf_counter()
        response: Response = await call_next(request)
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)

        response.headers["X-Request-ID"] = cid

        if request.url.path not in _SKIP_LOG:
            _log.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                latency_ms=latency_ms,
                correlation_id=cid,
                client=_real_ip(request),
            )

        return response


def _real_ip(request: Request) -> str:
    """Prefer X-Real-IP or the first X-Forwarded-For hop over the raw client IP."""
    if real_ip := request.headers.get("X-Real-IP"):
        return real_ip
    if forwarded := request.headers.get("X-Forwarded-For"):
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
