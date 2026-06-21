"""Hybrid retrieval — fuses BM25 and dense rankings via Reciprocal Rank Fusion.

Reciprocal Rank Fusion (RRF) formula (Cormack et al., 2009):
    rrf_score(d) = Σ_r  1 / (k + rank_r(d))
where k=60 (empirically robust constant) and rank_r is the 1-based rank in
retriever r.  RRF naturally normalises heterogeneous score scales, making it
the gold standard for combining sparse + dense rankings.
"""

from __future__ import annotations

from src.rag.base import Document, RetrievalResult, Retriever

_RRF_K = 60


class HybridRetriever(Retriever):
    """Combine any number of Retriever instances using RRF.

    Typical usage:
        hybrid = HybridRetriever([bm25, dense], k=5)
        results = hybrid.retrieve("query", k=5)
    """

    name = "hybrid_rrf"

    def __init__(self, retrievers: list[Retriever], rrf_k: int = _RRF_K) -> None:
        if not retrievers:
            raise ValueError("HybridRetriever requires at least one retriever")
        self._retrievers = retrievers
        self._rrf_k = rrf_k

    def add_documents(self, docs: list[Document]) -> None:
        for r in self._retrievers:
            r.add_documents(docs)

    def retrieve(self, query: str, k: int = 5) -> list[RetrievalResult]:
        # Fetch more candidates from each retriever to give RRF room to work
        fetch_k = k * 3
        rrf_scores: dict[str, float] = {}
        doc_map: dict[str, Document] = {}

        for retriever in self._retrievers:
            results = retriever.retrieve(query, k=fetch_k)
            for rank, res in enumerate(results, start=1):
                doc_key = f"{res.document.id}::{res.document.chunk_index}"
                rrf_scores[doc_key] = rrf_scores.get(doc_key, 0.0) + 1.0 / (self._rrf_k + rank)
                doc_map[doc_key] = res.document

        if not rrf_scores:
            return []

        sorted_keys = sorted(rrf_scores, key=lambda dk: rrf_scores[dk], reverse=True)[:k]
        max_score = rrf_scores[sorted_keys[0]] if sorted_keys else 1.0

        return [
            RetrievalResult(
                document=doc_map[dk],
                score=rrf_scores[dk] / max_score,
                retriever=self.name,
            )
            for dk in sorted_keys
        ]

    def clear(self) -> None:
        for r in self._retrievers:
            r.clear()
