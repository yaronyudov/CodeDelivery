"""LLM output guardrails — parse, validate, and record failures.

Every agent that calls an LLM should use parse_llm_json() or
parse_llm_json_list() instead of bare json.loads() so that:
  1. Markdown code-fences are stripped automatically.
  2. Pydantic validation runs and produces a typed object.
  3. Parse failures are recorded in an OTel counter (never silently swallowed).
  4. A safe typed default is returned on failure so callers never crash.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Matches ```json ... ``` or ``` ... ``` code fences (possibly with leading/trailing whitespace)
_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _strip_markdown(text: str) -> str:
    """Remove markdown code fences and return the inner content."""
    match = _FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    # Some models just wrap in backticks without a language tag
    stripped = text.strip().strip("`").strip()
    return stripped


def _record_parse_failure(context: str, reason: str) -> None:
    """Increment the parse-failure counter if OTel is available, then log."""
    try:
        from src.observability.tracing import (
            parse_failure_counter,  # avoid circular import at module load
        )

        parse_failure_counter.add(1, {"agent": context, "reason": reason})
    except Exception:
        pass  # OTel not configured — still log
    logger.warning("parse_llm_json failed", extra={"agent": context, "reason": reason})


def parse_llm_json(text: str, model_cls: type[T], context: str = "unknown") -> T:
    """Parse LLM text as JSON and validate against *model_cls*.

    Returns a default-constructed instance of *model_cls* on any failure.
    The caller should treat a returned default (i.e. model_cls()) as a
    degraded result and handle it appropriately.
    """
    cleaned = _strip_markdown(text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        _record_parse_failure(context, f"json_decode:{exc}")
        return model_cls()

    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        _record_parse_failure(context, f"validation:{exc.error_count()}_errors")
        # Try to build a partial model — Pydantic fills missing fields with defaults
        try:
            return model_cls.model_validate(data, strict=False)
        except ValidationError:
            return model_cls()


def parse_llm_json_list(text: str, item_cls: type[T], context: str = "unknown") -> list[T]:
    """Parse LLM text as a JSON array of *item_cls* objects.

    Invalid individual items are skipped (with a logged warning);
    returns an empty list if the outer structure is not a JSON array.
    """
    cleaned = _strip_markdown(text)
    try:
        raw = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        _record_parse_failure(context, f"json_decode:{exc}")
        return []

    if not isinstance(raw, list):
        _record_parse_failure(context, "not_an_array")
        return []

    results: list[T] = []
    for i, item in enumerate(raw):
        try:
            results.append(item_cls.model_validate(item))
        except ValidationError as exc:
            _record_parse_failure(context, f"item_{i}_validation:{exc.error_count()}_errors")
    return results
