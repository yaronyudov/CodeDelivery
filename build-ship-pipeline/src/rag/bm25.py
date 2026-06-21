"""BM25 retrieval — two implementations.

InMemoryBM25Retriever
    Pure-Python Okapi BM25 (Robertson et al., 1994).  No extra dependencies.
    Fast for corpora up to ~50 K chunks.  Score formula:
        score(D, Q) = Σ IDF(q) * tf(q,D)*(k1+1) / (tf(q,D) + k1*(1-b+b*|D|/avgdl))
    where IDF(q) = ln((N - df(q) + 0.5) / (df(q) + 0.5) + 1)

PostgresBM25Retriever
    Delegates to Postgres full-text search (ts_rank_cd) via the GIN index on
    rag_documents(content).  Scales to millions of rows without loading anything
    into memory.  Requires a live DB connection pool.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from src.rag.base import Document, RetrievalResult, Retriever

# BM25 tuning params (recommended defaults from literature)
_K1 = 1.5
_B = 0.75


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


# ---------------------------------------------------------------------------
# In-memory BM25
# ---------------------------------------------------------------------------


class InMemoryBM25Retriever(Retriever):
    """Okapi BM25 over an in-memory corpus.  Thread-safe for reads after indexing."""

    name = "bm25_memory"

    def __init__(self, k1: float = _K1, b: float = _B) -> None:
        self.k1 = k1
        self.b = b
        self._docs: list[Document] = []
        self._tf: list[dict[str, int]] = []  # term frequency per doc
        self._df: dict[str, int] = {}  # document frequency per term
        self._avgdl: float = 0.0

    def add_documents(self, docs: list[Document]) -> None:
        for doc in docs:
            tokens = _tokenize(doc.content)
            tf = Counter(tokens)
            self._docs.append(doc)
            self._tf.append(dict(tf))
            for term in set(tokens):
                self._df[term] = self._df.get(term, 0) + 1
        total = sum(sum(tf.values()) for tf in self._tf)
        self._avgdl = total / max(len(self._docs), 1)

    def retrieve(self, query: str, k: int = 5) -> list[RetrievalResult]:
        if not self._docs:
            return []
        q_terms = _tokenize(query)
        N = len(self._docs)
        scores: list[float] = []
        for i, tf in enumerate(self._tf):
            doc_len = sum(tf.values())
            score = 0.0
            for term in q_terms:
                if term not in tf:
                    continue
                df = self._df.get(term, 0)
                idf = math.log((N - df + 0.5) / (df + 0.5) + 1)
                tf_val = tf[term]
                score += (
                    idf
                    * (tf_val * (self.k1 + 1))
                    / (tf_val + self.k1 * (1 - self.b + self.b * doc_len / self._avgdl))
                )
            scores.append(score)

        top = sorted(range(N), key=lambda i: scores[i], reverse=True)[:k]
        max_score = scores[top[0]] if top and scores[top[0]] > 0 else 1.0
        return [
            RetrievalResult(
                document=self._docs[i],
                score=scores[i] / max_score,
                retriever=self.name,
            )
            for i in top
            if scores[i] > 0
        ]

    def clear(self) -> None:
        self._docs.clear()
        self._tf.clear()
        self._df.clear()
        self._avgdl = 0.0


# ---------------------------------------------------------------------------
# Postgres FTS BM25 (ts_rank_cd)
# ---------------------------------------------------------------------------


class PostgresBM25Retriever(Retriever):
    """BM25-equivalent retrieval via Postgres GIN full-text search.

    Requires the rag_documents table to exist (schema.sql ROLE 10).
    """

    name = "bm25_postgres"

    def __init__(self, pool: Any, corpus: str | None = None) -> None:
        """
        pool    — psycopg_pool.ConnectionPool
        corpus  — if set, restrict search to rag_documents.corpus = corpus
        """
        self._pool = pool
        self._corpus = corpus

    def add_documents(self, docs: list[Document]) -> None:
        import json

        rows = [
            (doc.id, d_idx, doc.content, json.dumps(doc.metadata), self._corpus or "custom")
            for d_idx, doc in enumerate(docs)
        ]
        with self._pool.connection() as conn:
            conn.executemany(
                """INSERT INTO rag_documents (doc_id, chunk_index, content, metadata, corpus)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (doc_id, chunk_index) DO UPDATE
                   SET content=EXCLUDED.content, metadata=EXCLUDED.metadata""",
                rows,
            )

    def retrieve(self, query: str, k: int = 5) -> list[RetrievalResult]:
        corpus_filter = "AND corpus = %s" if self._corpus else ""
        params: list[Any] = [query, k]
        if self._corpus:
            params = [query, self._corpus, k]

        sql = f"""
            SELECT doc_id, chunk_index, content, metadata,
                   ts_rank_cd(to_tsvector('english', content),
                              plainto_tsquery('english', %s)) AS rank
            FROM rag_documents
            WHERE to_tsvector('english', content) @@ plainto_tsquery('english', %s)
            {corpus_filter}
            ORDER BY rank DESC
            LIMIT %s
        """
        params = [query, query] + ([self._corpus] if self._corpus else []) + [k]

        from psycopg.rows import dict_row

        with self._pool.connection() as conn:
            rows = conn.execute(sql, params, row_factory=dict_row).fetchall()

        if not rows:
            return []
        max_rank = max(r["rank"] for r in rows) or 1.0
        return [
            RetrievalResult(
                document=Document(
                    id=r["doc_id"],
                    content=r["content"],
                    metadata=r["metadata"] or {},
                    chunk_index=r["chunk_index"],
                ),
                score=r["rank"] / max_rank,
                retriever=self.name,
            )
            for r in rows
        ]

    def clear(self) -> None:
        corpus_filter = "WHERE corpus = %s" if self._corpus else ""
        params = [self._corpus] if self._corpus else []
        with self._pool.connection() as conn:
            conn.execute(f"DELETE FROM rag_documents {corpus_filter}", params)
