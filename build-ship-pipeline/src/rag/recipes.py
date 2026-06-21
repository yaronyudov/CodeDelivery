"""Concrete RAG use cases for the Build & Ship pipeline.

The pipeline already has a long-term ``memory`` table (kinds: ``pattern``,
``past_plan``, ``lesson``) and a per-run ``knowledge`` table (topics:
``codebase_map``, ``known_cves``, …) that were previously write-only.  These
recipes turn them into a **cross-run learning loop**:

    ┌─────────────┐   persist_run_memory()   ┌────────────┐
    │ run N        │ ───────────────────────► │  memory    │
    │ (report)     │                          │  (DB)      │
    └─────────────┘                          └─────┬──────┘
                                                   │ retrieve_*()
    ┌─────────────┐                                ▼
    │ run N+1      │ ◄──────────  similar plans / lessons / patterns
    │ (planner …)  │
    └─────────────┘

Use cases
---------
1. retrieve_similar_plans   — Planner: reuse decompositions from past runs.
2. retrieve_debug_lessons   — Debugger: recall fixes for similar failures.
3. retrieve_code_patterns   — Coder: surface reusable code patterns.
4. retrieve_security_context— Security: graph/keyword recall over known CVEs
                              and the codebase map.
5. persist_run_memory       — Report: write this run's plan + lesson back to
                              memory so future runs can learn from it.

Every function is defensive: any DB/LLM/validation error yields an empty
string (or a no-op) so the pipeline never fails because of RAG.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from src.rag.base import Document
from src.rag.bm25 import InMemoryBM25Retriever
from src.rag.indexer import PipelineIndexer
from src.rag.instrument import InstrumentedRetriever

logger = logging.getLogger(__name__)

_MAX_CONTEXT_CHARS = 3000


def _bm25_over(rows: list[dict], to_text) -> InstrumentedRetriever:
    """Build an instrumented in-memory BM25 retriever over arbitrary rows."""
    retriever = InstrumentedRetriever(InMemoryBM25Retriever())
    docs = [
        Document(id=str(i), content=to_text(r), metadata=r)
        for i, r in enumerate(rows)
        if to_text(r).strip()
    ]
    if docs:
        retriever.add_documents(docs)
    return retriever


def _safe(fn):
    """Decorator: never let a recipe raise into the pipeline."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 — RAG must degrade, not crash
            logger.warning("RAG recipe %s failed: %s", fn.__name__, exc)
            return ""
    wrapper.__name__ = fn.__name__
    return wrapper


# ---------------------------------------------------------------------------
# Use case 1 — Planner: similar past plans
# ---------------------------------------------------------------------------

@_safe
def retrieve_similar_plans(feature_request: str, db: Any, k: int = 3) -> str:
    """Return formatted context of past plans most similar to *feature_request*."""
    if db is None or not feature_request.strip():
        return ""
    rows = db.list_memory(kinds=["past_plan"])
    if not rows:
        return ""
    retriever = _bm25_over(
        rows,
        to_text=lambda r: f"{r.get('key','')}\n{json.dumps(r.get('value', {}))}",
    )
    results = retriever.retrieve(feature_request, k=k)
    if not results:
        return ""
    body = PipelineIndexer.format_context(results, max_chars=_MAX_CONTEXT_CHARS)
    return body.replace("## Retrieved context", "## Similar past plans (reuse where applicable)")


# ---------------------------------------------------------------------------
# Use case 2 — Debugger: lessons from past failures
# ---------------------------------------------------------------------------

@_safe
def retrieve_debug_lessons(failures: list, db: Any, k: int = 3) -> str:
    """Return lessons learned from past test failures similar to *failures*."""
    if db is None or not failures:
        return ""
    rows = db.list_memory(kinds=["lesson"])
    if not rows:
        return ""
    query = " ".join(str(f) for f in failures)[:2000]
    retriever = _bm25_over(
        rows,
        to_text=lambda r: f"{r.get('key','')}\n{json.dumps(r.get('value', {}))}",
    )
    results = retriever.retrieve(query, k=k)
    if not results:
        return ""
    body = PipelineIndexer.format_context(results, max_chars=_MAX_CONTEXT_CHARS)
    return body.replace("## Retrieved context", "## Lessons from past similar failures")


# ---------------------------------------------------------------------------
# Use case 3 — Coder: reusable code patterns
# ---------------------------------------------------------------------------

@_safe
def retrieve_code_patterns(plan: dict, db: Any, k: int = 3) -> str:
    """Return reusable code patterns relevant to the current plan."""
    if db is None or not plan:
        return ""
    rows = db.list_memory(kinds=["pattern"])
    if not rows:
        return ""
    query = f"{plan.get('summary','')} {' '.join(plan.get('tech_stack', []))}"
    retriever = _bm25_over(
        rows,
        to_text=lambda r: f"{r.get('key','')}\n{json.dumps(r.get('value', {}))}",
    )
    results = retriever.retrieve(query or "code pattern", k=k)
    if not results:
        return ""
    body = PipelineIndexer.format_context(results, max_chars=_MAX_CONTEXT_CHARS)
    return body.replace("## Retrieved context", "## Reusable code patterns")


# ---------------------------------------------------------------------------
# Use case 4 — Security: recall over knowledge base (CVEs + codebase map)
# ---------------------------------------------------------------------------

@_safe
def retrieve_security_context(query: str, db: Any, run_id: str, k: int = 5) -> str:
    """Return relevant known-CVE / codebase-map context for the security auditor."""
    if db is None or not query.strip() or not run_id:
        return ""
    rows = db.list_knowledge(run_id)
    relevant = [r for r in rows if r.get("topic") in ("known_cves", "codebase_map")]
    if not relevant:
        return ""
    retriever = _bm25_over(
        relevant,
        to_text=lambda r: f"{r.get('topic','')}\n{json.dumps(r.get('payload', {}))}",
    )
    results = retriever.retrieve(query, k=k)
    if not results:
        return ""
    body = PipelineIndexer.format_context(results, max_chars=_MAX_CONTEXT_CHARS)
    return body.replace("## Retrieved context", "## Known CVEs & codebase map (security context)")


# ---------------------------------------------------------------------------
# Use case 5 — Report: persist this run's plan + lesson for future runs
# ---------------------------------------------------------------------------

@_safe
def persist_run_memory(state: dict, db: Any) -> bool:
    """Write the completed run's plan and a distilled lesson back to memory.

    Returns True if anything was written.  Called from report_node on success.
    """
    if db is None:
        return False
    run_id = state.get("run_id", "unknown")
    plan = state.get("plan", {})
    feature = state.get("feature_request", "")
    wrote = False

    if plan:
        db.save_memory(
            kind="past_plan",
            key=feature[:200] or run_id,
            value={
                "run_id": run_id,
                "feature_request": feature,
                "summary": plan.get("summary", ""),
                "tech_stack": plan.get("tech_stack", []),
                "tasks": plan.get("tasks", []),
                "verdict": state.get("verdict"),
            },
        )
        wrote = True

    # Distil a lesson from review findings (the most valuable cross-run signal).
    findings = state.get("findings", [])
    significant = [f for f in findings if f.get("severity") in ("critical", "major")]
    if significant:
        db.save_memory(
            kind="lesson",
            key=feature[:200] or run_id,
            value={
                "run_id": run_id,
                "feature_request": feature,
                "lessons": [
                    {"agent": f.get("agent"), "severity": f.get("severity"),
                     "message": f.get("message"), "location": f.get("location")}
                    for f in significant
                ],
            },
        )
        wrote = True

    return wrote
