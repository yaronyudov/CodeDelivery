"""LLM-based reranker — cross-encoder–style relevance scoring.

After any retriever produces a candidate list, the reranker asks the LLM to
score each candidate for relevance to the original query on a 1–5 scale, then
re-sorts the list.

This corrects errors from BM25/dense retrieval (which use coarse proxies for
relevance) at the cost of one extra LLM call per reranking operation.

Typical usage
-------------
    retriever = HybridRetriever([bm25, dense])
    reranker = LLMReranker(model="anthropic/claude-haiku-4-5-20251001")

    candidates = retriever.retrieve(query, k=20)     # fetch more candidates
    final = reranker.rerank(query, candidates, k=5)  # rerank, keep top-5

The reranker is also exposed as a Retriever subclass so it can wrap any base:
    reranker_retriever = LLMReranker(model=..., base=hybrid)
    results = reranker_retriever.retrieve(query, k=5)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.rag.base import Document, RetrievalResult, Retriever

logger = logging.getLogger(__name__)

_RERANK_SYSTEM = """You are a relevance judge.  Given a query and a document excerpt, score the
document's relevance to the query on a scale from 1 to 5:
  5 = Directly and fully answers the query.
  4 = Highly relevant, answers most of the query.
  3 = Partially relevant — useful but incomplete.
  2 = Tangentially related — mentions the topic but doesn't help much.
  1 = Not relevant.

Respond with a JSON object: {"score": <1-5>, "reason": "<one sentence>"}
Respond ONLY with valid JSON."""


def _score_one(
    query: str,
    content: str,
    model: str,
    api_key: str | None,
    api_base: str | None,
) -> float:
    import litellm

    litellm.suppress_debug_info = True
    user_msg = f"Query: {query}\n\nDocument excerpt:\n{content[:1000]}"
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": _RERANK_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        "max_tokens": 128,
    }
    if api_key:
        kwargs["api_key"] = api_key
    if api_base:
        kwargs["api_base"] = api_base
    try:
        resp = litellm.completion(**kwargs)
        text = resp.choices[0].message.content or ""
        cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().strip("`")
        data = json.loads(cleaned)
        return float(data.get("score", 1)) / 5.0
    except Exception as exc:
        logger.debug("reranker scoring failed: %s", exc)
        return 0.5  # neutral on failure


class LLMReranker:
    """Re-score a list of RetrievalResult objects using an LLM judge."""

    def __init__(
        self,
        model: str = "anthropic/claude-haiku-4-5-20251001",
        api_key: str | None = None,
        api_base: str | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.api_base = api_base

    def rerank(
        self,
        query: str,
        candidates: list[RetrievalResult],
        k: int | None = None,
    ) -> list[RetrievalResult]:
        """Score each candidate and return them sorted by LLM relevance score."""
        if not candidates:
            return []
        rescored: list[RetrievalResult] = []
        for res in candidates:
            score = _score_one(query, res.document.content, self.model, self.api_key, self.api_base)
            rescored.append(
                RetrievalResult(document=res.document, score=score, retriever="reranker")
            )
        rescored.sort(key=lambda r: r.score, reverse=True)
        return rescored[:k] if k else rescored


class RerankedRetriever(Retriever):
    """Compose a base retriever with an LLM reranker in a single Retriever interface.

    Fetches ``fetch_k`` candidates from *base*, then reranks to top *k*.
    """

    name = "reranked"

    def __init__(
        self,
        base: Retriever,
        reranker: LLMReranker,
        fetch_k: int = 20,
    ) -> None:
        self._base = base
        self._reranker = reranker
        self._fetch_k = fetch_k

    def add_documents(self, docs: list[Document]) -> None:
        self._base.add_documents(docs)

    def retrieve(self, query: str, k: int = 5) -> list[RetrievalResult]:
        candidates = self._base.retrieve(query, k=self._fetch_k)
        return self._reranker.rerank(query, candidates, k=k)

    def clear(self) -> None:
        self._base.clear()
