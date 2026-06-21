"""HyDE — Hypothetical Document Embeddings (Gao et al., 2022).

Instead of embedding the query directly, the LLM generates a *hypothetical*
answer that the query is looking for, then that answer is embedded and used
for similarity search.  This bridges the vocabulary gap between short queries
and longer document chunks.

Algorithm
---------
1. Prompt the LLM: "Write a paragraph that directly answers: <query>"
2. Embed the hypothetical paragraph.
3. Run the wrapped dense retriever with that embedding as the query.

HyDE improves recall especially for:
- Short, keyword-style queries ("JWT authentication bug")
- Domain-specific queries where the exact terminology is in the corpus
- Questions where the answer phrasing differs from the question phrasing
"""

from __future__ import annotations

import logging
from typing import Any

from src.rag.base import Document, RetrievalResult, Retriever

logger = logging.getLogger(__name__)

_HYDE_SYSTEM = """Write a short technical paragraph (3-5 sentences) that directly and specifically
answers the following query.  Be factual and precise — imagine you are writing documentation.
Do not start with "This paragraph" or similar meta-phrases.  Answer directly."""


def _generate_hypothesis(
    query: str,
    model: str,
    api_key: str | None,
    api_base: str | None,
) -> str:
    import litellm

    litellm.suppress_debug_info = True
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": _HYDE_SYSTEM},
            {"role": "user", "content": query},
        ],
        "max_tokens": 256,
    }
    if api_key:
        kwargs["api_key"] = api_key
    if api_base:
        kwargs["api_base"] = api_base
    try:
        resp = litellm.completion(**kwargs)
        return resp.choices[0].message.content or query
    except Exception as exc:
        logger.warning("HyDE LLM call failed: %s", exc)
        return query  # graceful degradation: use original query


class HyDERetriever(Retriever):
    """Wrap any dense retriever with hypothetical document expansion.

    Parameters
    ----------
    base_retriever : Retriever
        A dense retriever (InMemoryDenseRetriever or PgVectorRetriever).
    gen_model : str
        LLM model to generate hypothetical documents (defaults to haiku for cost).
    api_key / api_base : str | None
        Optional LLM credentials (reuse state["model_config"] values).
    """

    name = "hyde"

    def __init__(
        self,
        base_retriever: Retriever,
        gen_model: str = "anthropic/claude-haiku-4-5-20251001",
        api_key: str | None = None,
        api_base: str | None = None,
    ) -> None:
        self._base = base_retriever
        self._gen_model = gen_model
        self._api_key = api_key
        self._api_base = api_base

    def add_documents(self, docs: list[Document]) -> None:
        self._base.add_documents(docs)

    def retrieve(self, query: str, k: int = 5) -> list[RetrievalResult]:
        hypothesis = _generate_hypothesis(query, self._gen_model, self._api_key, self._api_base)
        results = self._base.retrieve(hypothesis, k=k)
        # Re-tag retriever name so callers know HyDE was used
        return [
            RetrievalResult(document=r.document, score=r.score, retriever=self.name)
            for r in results
        ]

    def clear(self) -> None:
        self._base.clear()
