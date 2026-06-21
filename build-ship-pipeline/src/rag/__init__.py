"""RAG module — pluggable retrieval-augmented generation strategies.

Supported strategies
--------------------
``bm25``          In-memory Okapi BM25 (pure Python, no extra deps)
``bm25_pg``       Postgres full-text search BM25 (GIN index, needs pool)
``dense``         Dense embedding retrieval in-memory (litellm embeddings)
``pgvector``      Dense embedding retrieval via pgvector (needs pool + extension)
``hybrid``        RRF fusion of BM25 + dense (recommended default)
``graph``         In-memory entity graph RAG
``graph_pg``      Postgres-backed entity graph RAG
``hyde``          HyDE: hypothetical document expansion before dense retrieval
``multi_query``   Multi-query expansion over any base retriever
``reranked``      LLM reranker on top of any base retriever

Quick start
-----------
    from src.rag import create_retriever, retrieve_for_agent
    from src.rag.indexer import PipelineIndexer

    # Build a retriever (no DB needed for default hybrid mode)
    retriever = create_retriever("hybrid")

    # Index the current run
    indexer = PipelineIndexer(retriever)
    indexer.index_state(state, db)

    # Retrieve and format context for injection into a system prompt
    results = retriever.retrieve("authentication JWT", k=5)
    context = PipelineIndexer.format_context(results)
    system = f"{_SYSTEM}\\n\\n{context}"

    # Or use the one-liner helper inside an agent
    context = retrieve_for_agent(query="JWT auth", state=state, db=db, k=5)
"""

from __future__ import annotations

from typing import Any

from src.rag.base import Document, RetrievalResult, Retriever
from src.rag.bm25 import InMemoryBM25Retriever, PostgresBM25Retriever
from src.rag.chunker import FixedChunker, RecursiveChunker, SentenceChunker
from src.rag.dense import InMemoryDenseRetriever, PgVectorRetriever
from src.rag.graph import InMemoryGraphRetriever, PostgresGraphRetriever
from src.rag.hybrid import HybridRetriever
from src.rag.hyde import HyDERetriever
from src.rag.indexer import PipelineIndexer
from src.rag.instrument import InstrumentedRetriever
from src.rag.multi_query import MultiQueryRetriever
from src.rag.reranker import LLMReranker, RerankedRetriever

__all__ = [
    # Types
    "Document",
    "Retriever",
    "RetrievalResult",
    # Chunkers
    "FixedChunker",
    "SentenceChunker",
    "RecursiveChunker",
    # Retrievers
    "InMemoryBM25Retriever",
    "PostgresBM25Retriever",
    "InMemoryDenseRetriever",
    "PgVectorRetriever",
    "HybridRetriever",
    "InMemoryGraphRetriever",
    "PostgresGraphRetriever",
    "HyDERetriever",
    "MultiQueryRetriever",
    "LLMReranker",
    "RerankedRetriever",
    "InstrumentedRetriever",
    # Indexer
    "PipelineIndexer",
    # Factory
    "create_retriever",
    "retrieve_for_agent",
]


def create_retriever(
    strategy: str = "hybrid",
    *,
    pool: Any = None,
    corpus: str | None = None,
    embedding_model: str = "text-embedding-3-small",
    gen_model: str = "anthropic/claude-haiku-4-5-20251001",
    api_key: str | None = None,
    api_base: str | None = None,
    run_id: str | None = None,
    n_variants: int = 3,
    fetch_k: int = 20,
    max_hops: int = 2,
    instrument: bool = True,
) -> Retriever:
    """Factory: create the right retriever for *strategy*.

    Parameters
    ----------
    strategy : str
        One of: bm25, bm25_pg, dense, pgvector, hybrid, graph, graph_pg,
        hyde, multi_query, reranked.
    pool : ConnectionPool | None
        Required for *_pg strategies.
    embedding_model : str
        litellm model string for embeddings.
    gen_model : str
        litellm model string for LLM-based strategies (HyDE, graph, multi_query, reranker).
    instrument : bool
        Wrap the result in InstrumentedRetriever (OTel spans/metrics + input
        validation).  Defaults to True; pass False for raw retrievers in tests.
    """
    from src.rag.guards import validate_corpus
    from src.rag.instrument import InstrumentedRetriever

    corpus = validate_corpus(corpus)
    inner = _build_retriever(
        strategy,
        pool=pool,
        corpus=corpus,
        embedding_model=embedding_model,
        gen_model=gen_model,
        api_key=api_key,
        api_base=api_base,
        run_id=run_id,
        n_variants=n_variants,
        fetch_k=fetch_k,
        max_hops=max_hops,
    )
    return InstrumentedRetriever(inner) if instrument else inner


def _build_retriever(
    strategy: str,
    *,
    pool: Any,
    corpus: str | None,
    embedding_model: str,
    gen_model: str,
    api_key: str | None,
    api_base: str | None,
    run_id: str | None,
    n_variants: int,
    fetch_k: int,
    max_hops: int,
) -> Retriever:
    s = strategy.lower()

    if s == "bm25":
        return InMemoryBM25Retriever()

    if s == "bm25_pg":
        if pool is None:
            raise ValueError("bm25_pg requires a pool")
        return PostgresBM25Retriever(pool=pool, corpus=corpus)

    if s == "dense":
        return InMemoryDenseRetriever(model=embedding_model, api_key=api_key, api_base=api_base)

    if s == "pgvector":
        if pool is None:
            raise ValueError("pgvector requires a pool")
        return PgVectorRetriever(
            pool=pool, model=embedding_model, api_key=api_key, api_base=api_base, corpus=corpus
        )

    if s == "hybrid":
        bm25 = InMemoryBM25Retriever()
        dense = InMemoryDenseRetriever(model=embedding_model, api_key=api_key, api_base=api_base)
        return HybridRetriever([bm25, dense])

    if s == "hybrid_pg":
        if pool is None:
            raise ValueError("hybrid_pg requires a pool")
        bm25 = PostgresBM25Retriever(pool=pool, corpus=corpus)
        dense_r = PgVectorRetriever(
            pool=pool, model=embedding_model, api_key=api_key, api_base=api_base, corpus=corpus
        )
        return HybridRetriever([bm25, dense_r])

    if s == "graph":
        return InMemoryGraphRetriever(
            model=gen_model, api_key=api_key, api_base=api_base, max_hops=max_hops
        )

    if s == "graph_pg":
        if pool is None:
            raise ValueError("graph_pg requires a pool")
        return PostgresGraphRetriever(
            pool=pool,
            model=gen_model,
            api_key=api_key,
            api_base=api_base,
            corpus=corpus or "custom",
            run_id=run_id,
            max_hops=max_hops,
        )

    if s == "hyde":
        dense = InMemoryDenseRetriever(model=embedding_model, api_key=api_key, api_base=api_base)
        return HyDERetriever(
            base_retriever=dense, gen_model=gen_model, api_key=api_key, api_base=api_base
        )

    if s == "multi_query":
        bm25 = InMemoryBM25Retriever()
        return MultiQueryRetriever(
            base_retriever=bm25,
            n_variants=n_variants,
            gen_model=gen_model,
            api_key=api_key,
            api_base=api_base,
        )

    if s == "reranked":
        hybrid = HybridRetriever(
            [
                InMemoryBM25Retriever(),
                InMemoryDenseRetriever(model=embedding_model, api_key=api_key, api_base=api_base),
            ]
        )
        reranker = LLMReranker(model=gen_model, api_key=api_key, api_base=api_base)
        return RerankedRetriever(base=hybrid, reranker=reranker, fetch_k=fetch_k)

    raise ValueError(
        f"Unknown RAG strategy: {strategy!r}. "
        "Valid options: bm25, bm25_pg, dense, pgvector, hybrid, hybrid_pg, "
        "graph, graph_pg, hyde, multi_query, reranked"
    )


# ---------------------------------------------------------------------------
# Agent-facing one-liner
# ---------------------------------------------------------------------------

_DEFAULT_STRATEGY = "bm25"  # cheapest default: no embedding API calls


def retrieve_for_agent(
    query: str,
    state: dict,
    db: Any,
    k: int = 5,
    strategy: str = _DEFAULT_STRATEGY,
    max_chars: int = 4000,
) -> str:
    """Index the current run and retrieve context in one call.

    Returns a formatted string suitable for appending to an agent's system prompt.
    Falls back to "" on any error so agents never crash due to RAG failures.
    """
    try:
        cfg = state.get("model_config") or {}
        retriever = create_retriever(
            strategy,
            api_key=cfg.get("api_key"),
            api_base=cfg.get("api_base"),
        )
        indexer = PipelineIndexer(retriever)
        indexer.index_state(state, db)
        results = retriever.retrieve(query, k=k)
        return PipelineIndexer.format_context(results, max_chars=max_chars)
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning("retrieve_for_agent failed: %s", exc)
        return ""
