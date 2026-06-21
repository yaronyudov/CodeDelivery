"""Structured JSON logging for the pipeline.

Usage:
    from src.observability.logger import get_logger
    log = get_logger(__name__)
    log.info("coder finished", run_id="abc", agent="coder", artifact_count=5)

All keyword arguments become top-level JSON fields.  Standard library
logging is used under the hood so the same logger works in tests.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any


class _JsonFormatter(logging.Formatter):
    """Emits one JSON object per line (logfmt-compatible with most collectors)."""

    def format(self, record: logging.LogRecord) -> str:
        base: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Extra fields injected via extra={} or structlog-style kwargs
        for key, val in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs", "message",
                "pathname", "process", "processName", "relativeCreated",
                "thread", "threadName", "exc_info", "exc_text", "stack_info",
                "taskName",
            }:
                base[key] = val
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return json.dumps(base, default=str)


def _configure_root() -> None:
    """Wire up the root logger once; safe to call multiple times."""
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)


_configure_root()


class _ContextLogger:
    """Thin wrapper that binds static context fields to every log call."""

    def __init__(self, name: str, **bound: Any) -> None:
        self._log = logging.getLogger(name)
        self._bound = bound

    def _emit(self, level: int, msg: str, **extra: Any) -> None:
        merged = {**self._bound, **extra}
        self._log.log(level, msg, extra=merged)

    def debug(self, msg: str, **kw: Any) -> None:
        self._emit(logging.DEBUG, msg, **kw)

    def info(self, msg: str, **kw: Any) -> None:
        self._emit(logging.INFO, msg, **kw)

    def warning(self, msg: str, **kw: Any) -> None:
        self._emit(logging.WARNING, msg, **kw)

    def error(self, msg: str, **kw: Any) -> None:
        self._emit(logging.ERROR, msg, **kw)

    def exception(self, msg: str, **kw: Any) -> None:
        self._log.exception(msg, extra={**self._bound, **kw})

    def bind(self, **extra: Any) -> "_ContextLogger":
        """Return a child logger with additional bound fields."""
        return _ContextLogger(self._log.name, **{**self._bound, **extra})


def get_logger(name: str, **bound: Any) -> _ContextLogger:
    """Return a structured logger bound to optional context fields."""
    return _ContextLogger(name, **bound)
