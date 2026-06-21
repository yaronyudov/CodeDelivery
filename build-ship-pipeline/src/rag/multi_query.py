"""Multi-Query RAG — query expansion via LLM-generated variants.

Algorithm (Ma et al., 2023)
---------------------------
1. LLM generates N rephrased/expanded versions of the original query.
2. Each query variant is run through the base retriever.
3. Results from all queries are unioned and deduplicated by (doc_id, chunk_index).
4. Union is re-scored using a simple vote count: a document that appears in
   the results of 3 out of 4 query variants scores higher than one that
   appeared once.

When to use
-----------
- Queries where the user might have used different terminology than the corpus.
- When a single query misses related concepts (e.g. "security" vs "auth" vs "JWT").
- As a pre-rerank expansion step before the LLM reranker.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from src.rag.base import Document, RetrievalResult, Retriever

logger = logging.getLogger(__name__)

_EXPAND_SYSTEM = """Generate {n} alternative phrasings of the following search query.
Each rephrasing should capture a slightly different angle or vocabulary.

Respond with a JSON array of strings: ["query 1", "query 2", ...]

Respond ONLY with the JSON array."""


def _expand_query(
    query: str,
    n: int,
    model: str,
    api_key: str | None,
    api_base: str | None,
) -> list[str]:
    import json
    import litellm
    litellm.suppress_debug_info = True
    system = _EXPAND_SYSTEM.format(n=n)
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": query},
        ],
        "max_tokens": 512,
    }
    if api_key:
        kwargs["api_key"] = api_key
    if api_base:
        kwargs["api_base"] = api_base
    try:
        resp = litellm.completion(**kwargs)
        text = resp.choices[0].message.content or "[]"
        cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().strip("`")
        variants: list[str] = json.loads(cleaned)
        if isinstance(variants, list):
            return [str(v) for v in variants if v]
    except Exception as exc:
        logger.warning("multi_query expansion failed: %s", exc)
    return []


class MultiQueryRetriever(Retriever):
    """Expand a query into N variants, retrieve for each, merge with vote scoring.

    Parameters
    ----------
    base_retriever : Retriever
        Any retriever.  Called once per query variant.
    n_variants : int
        Number of additional query variants (total queries = n_variants + 1).
    gen_model : str
        LLM model for expansion (defaults to haiku for cost).
    """

    name = "multi_query"

    def __init__(
        self,
        base_retriever: Retriever,
        n_variants: int = 3,
        gen_model: str = "anthropic/claude-haiku-4-5-20251001",
        api_key: str | None = None,
        api_base: str | None = None,
    ) -> None:
        self._base = base_retriever
        self._n = n_variants
        self._gen_model = gen_model
        self._api_key = api_key
        self._api_base = api_base

    def add_documents(self, docs: list[Document]) -> None:
        self._base.add_documents(docs)

    def retrieve(self, query: str, k: int = 5) -> list[RetrievalResult]:
        variants = _expand_query(query, self._n, self._gen_model, self._api_key, self._api_base)
        all_queries = [query] + variants

        votes: dict[str, int] = {}
        best_score: dict[str, float] = {}
        doc_map: dict[str, Document] = {}

        for q in all_queries:
            for res in self._base.retrieve(q, k=k):
                key = f"{res.document.id}::{res.document.chunk_index}"
                votes[key] = votes.get(key, 0) + 1
                if res.score > best_score.get(key, 0.0):
                    best_score[key] = res.score
                doc_map[key] = res.document

        if not votes:
            return []

        n_queries = len(all_queries)
        # Combined score: vote fraction * best score
        combined = {
            key: (votes[key] / n_queries) * best_score[key]
            for key in votes
        }
        sorted_keys = sorted(combined, key=lambda dk: combined[dk], reverse=True)[:k]
        max_score = combined[sorted_keys[0]] if sorted_keys else 1.0

        return [
            RetrievalResult(
                document=doc_map[dk],
                score=combined[dk] / max_score,
                retriever=self.name,
            )
            for dk in sorted_keys
        ]

    def clear(self) -> None:
        self._base.clear()
