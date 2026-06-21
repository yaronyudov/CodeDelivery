"""InstrumentedRetriever — observability + input validation wrapper.

Wraps any Retriever so that every retrieve()/add_documents() call:
  - validates inputs via src.rag.guards (query length, k bounds)
  - opens an OTel span with retriever + result-count attributes
  - records latency + retrieval counters via src.observability.tracing
  - caps the number of indexed chunks per call against the doc-size guard

The factory (src.rag.create_retriever) applies this wrapper by default so
all strategies are observable and guarded without per-retriever code.
"""
from __future__ import annotations

import time

from src.rag.base import Document, RetrievalResult, Retriever
from src.rag.guards import MAX_DOC_CHARS, validate_k, validate_query


class InstrumentedRetriever(Retriever):
    """Transparent wrapper adding tracing + validation to any retriever."""

    def __init__(self, inner: Retriever) -> None:
        self._inner = inner
        # Surface the wrapped retriever's name so metrics/labels stay meaningful.
        self.name = f"{inner.name}"

    def add_documents(self, docs: list[Document]) -> None:
        # Drop oversize chunks defensively rather than failing the whole batch.
        safe_docs = [d for d in docs if len(d.content) <= MAX_DOC_CHARS]
        try:
            from src.observability.tracing import rag_documents_indexed, tracer
            with tracer.start_as_current_span("rag.index") as span:
                span.set_attribute("retriever", self._inner.name)
                span.set_attribute("documents", len(safe_docs))
                span.set_attribute("dropped", len(docs) - len(safe_docs))
                self._inner.add_documents(safe_docs)
            rag_documents_indexed.add(len(safe_docs), {"retriever": self._inner.name})
        except Exception:
            # Observability must never break indexing.
            self._inner.add_documents(safe_docs)

    def retrieve(self, query: str, k: int = 5) -> list[RetrievalResult]:
        query = validate_query(query)
        k = validate_k(k)

        t0 = time.perf_counter()
        try:
            from src.observability.tracing import record_rag_retrieval, tracer
            with tracer.start_as_current_span("rag.retrieve") as span:
                span.set_attribute("retriever", self._inner.name)
                span.set_attribute("k", k)
                span.set_attribute("query_chars", len(query))
                results = self._inner.retrieve(query, k=k)
                span.set_attribute("results", len(results))
            record_rag_retrieval(self._inner.name, len(results), time.perf_counter() - t0)
            return results
        except ImportError:
            # OTel not installed — still serve results.
            return self._inner.retrieve(query, k=k)

    def clear(self) -> None:
        self._inner.clear()
