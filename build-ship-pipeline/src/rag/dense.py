"""Dense embedding retriever.

Strategy
--------
1. Embed each document chunk using `litellm.embedding()`.
2. Store embeddings in-memory (numpy array) OR in Postgres via pgvector.
3. At query time, embed the query and return top-k by cosine similarity.

Model configuration
-------------------
Default: ``text-embedding-3-small`` (OpenAI).  Override via the
``embedding_model`` constructor argument or the ``EMBEDDING_MODEL`` env var.
Any litellm-compatible embedding model string is accepted.

pgvector mode
-------------
Set ``use_pgvector=True`` and provide a ``pool`` (psycopg3 ConnectionPool).
The ``embedding`` column must be enabled in ``rag_documents`` first:
    ALTER TABLE rag_documents ADD COLUMN embedding VECTOR(1536);
    CREATE INDEX ON rag_documents USING ivfflat (embedding vector_cosine_ops);
"""
from __future__ import annotations

import math
import os
from typing import Any

from src.rag.base import Document, RetrievalResult, Retriever

_DEFAULT_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")


def _embed(texts: list[str], model: str, api_key: str | None, api_base: str | None) -> list[list[float]]:
    import litellm
    litellm.suppress_debug_info = True
    kwargs: dict[str, Any] = {"model": model, "input": texts}
    if api_key:
        kwargs["api_key"] = api_key
    if api_base:
        kwargs["api_base"] = api_base
    resp = litellm.embedding(**kwargs)
    return [item["embedding"] for item in resp.data]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# In-memory dense retriever
# ---------------------------------------------------------------------------

class InMemoryDenseRetriever(Retriever):
    """Embed documents and retrieve by cosine similarity (no DB required)."""

    name = "dense_memory"

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        api_key: str | None = None,
        api_base: str | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.api_base = api_base
        self._docs: list[Document] = []
        self._embeddings: list[list[float]] = []

    def add_documents(self, docs: list[Document]) -> None:
        if not docs:
            return
        texts = [d.content for d in docs]
        vecs = _embed(texts, self.model, self.api_key, self.api_base)
        self._docs.extend(docs)
        self._embeddings.extend(vecs)

    def retrieve(self, query: str, k: int = 5) -> list[RetrievalResult]:
        if not self._docs:
            return []
        q_vec = _embed([query], self.model, self.api_key, self.api_base)[0]
        scored = [
            (i, _cosine(q_vec, emb)) for i, emb in enumerate(self._embeddings)
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [
            RetrievalResult(document=self._docs[i], score=max(0.0, s), retriever=self.name)
            for i, s in scored[:k]
        ]

    def clear(self) -> None:
        self._docs.clear()
        self._embeddings.clear()


# ---------------------------------------------------------------------------
# pgvector dense retriever
# ---------------------------------------------------------------------------

class PgVectorRetriever(Retriever):
    """Store embeddings in Postgres rag_documents.embedding (pgvector).

    Requires: ALTER TABLE rag_documents ADD COLUMN embedding VECTOR(<dim>);
    and the pgvector extension to be loaded.
    """

    name = "dense_pgvector"

    def __init__(
        self,
        pool: Any,
        model: str = _DEFAULT_MODEL,
        api_key: str | None = None,
        api_base: str | None = None,
        corpus: str | None = None,
    ) -> None:
        self._pool = pool
        self.model = model
        self.api_key = api_key
        self.api_base = api_base
        self._corpus = corpus

    def add_documents(self, docs: list[Document]) -> None:
        if not docs:
            return
        import json
        texts = [d.content for d in docs]
        vecs = _embed(texts, self.model, self.api_key, self.api_base)
        corpus = self._corpus or "custom"
        rows = [
            (doc.id, doc.chunk_index, doc.content, json.dumps(doc.metadata), corpus, str(vec))
            for doc, vec in zip(docs, vecs)
        ]
        with self._pool.connection() as conn:
            conn.executemany(
                """INSERT INTO rag_documents
                   (doc_id, chunk_index, content, metadata, corpus, embedding)
                   VALUES (%s, %s, %s, %s, %s, %s::vector)
                   ON CONFLICT (doc_id, chunk_index) DO UPDATE
                   SET content=EXCLUDED.content, embedding=EXCLUDED.embedding""",
                rows,
            )

    def retrieve(self, query: str, k: int = 5) -> list[RetrievalResult]:
        q_vec = _embed([query], self.model, self.api_key, self.api_base)[0]
        corpus_filter = "AND corpus = %s" if self._corpus else ""
        params: list[Any] = [str(q_vec)]
        if self._corpus:
            params.append(self._corpus)
        params.append(k)
        sql = f"""
            SELECT doc_id, chunk_index, content, metadata,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM rag_documents
            WHERE embedding IS NOT NULL {corpus_filter}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        params = [str(q_vec)] + ([self._corpus] if self._corpus else []) + [str(q_vec), k]
        from psycopg.rows import dict_row
        with self._pool.connection() as conn:
            rows = conn.execute(sql, params, row_factory=dict_row).fetchall()
        return [
            RetrievalResult(
                document=Document(
                    id=r["doc_id"], content=r["content"],
                    metadata=r["metadata"] or {}, chunk_index=r["chunk_index"],
                ),
                score=max(0.0, float(r["similarity"])),
                retriever=self.name,
            )
            for r in rows
        ]

    def clear(self) -> None:
        corpus_filter = "WHERE corpus = %s" if self._corpus else ""
        params = [self._corpus] if self._corpus else []
        with self._pool.connection() as conn:
            conn.execute(f"DELETE FROM rag_documents {corpus_filter}", params)
