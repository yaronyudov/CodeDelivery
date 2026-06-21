"""Unit tests for the RAG module — no LLM calls, no DB required."""
from __future__ import annotations

import pytest

from src.rag.base import Document, RetrievalResult
from src.rag.bm25 import InMemoryBM25Retriever, _tokenize
from src.rag.chunker import FixedChunker, RecursiveChunker, SentenceChunker
from src.rag.hybrid import HybridRetriever


# ---------------------------------------------------------------------------
# Chunker tests
# ---------------------------------------------------------------------------

def test_fixed_chunker_splits_correctly():
    chunker = FixedChunker(chunk_size=10, overlap=2)
    docs = chunker.chunk("doc1", "abcdefghijklmnopqrstuvwxyz")
    assert len(docs) > 1
    assert all(len(d.content) <= 10 for d in docs)
    assert all(d.id == "doc1" for d in docs)


def test_fixed_chunker_short_content_single_chunk():
    chunker = FixedChunker(chunk_size=100, overlap=10)
    docs = chunker.chunk("doc2", "hello world")
    assert len(docs) == 1
    assert docs[0].content == "hello world"


def test_sentence_chunker_groups_sentences():
    chunker = SentenceChunker(max_sentences=2, overlap_sentences=0)
    text = "First sentence. Second sentence. Third sentence. Fourth sentence."
    docs = chunker.chunk("doc3", text)
    assert len(docs) == 2
    assert "First" in docs[0].content


def test_recursive_chunker_short_content():
    chunker = RecursiveChunker(target_size=200, overlap=0)
    docs = chunker.chunk("doc4", "A short text.")
    assert len(docs) == 1
    assert docs[0].content == "A short text."


def test_recursive_chunker_long_content():
    chunker = RecursiveChunker(target_size=20, overlap=0)
    text = "word " * 40  # 200 chars
    docs = chunker.chunk("doc5", text)
    assert len(docs) > 1
    assert all(d.id == "doc5" for d in docs)


def test_chunk_index_is_sequential():
    chunker = FixedChunker(chunk_size=5, overlap=0)
    docs = chunker.chunk("idx-test", "abcdefghij")
    for expected, doc in enumerate(docs):
        assert doc.chunk_index == expected


# ---------------------------------------------------------------------------
# BM25 tests
# ---------------------------------------------------------------------------

def test_tokenize_lowercases_and_splits():
    tokens = _tokenize("Hello World! This is a TEST.")
    assert "hello" in tokens
    assert "world" in tokens
    assert "test" in tokens
    assert "!" not in tokens


def test_bm25_returns_most_relevant_doc():
    retriever = InMemoryBM25Retriever()
    retriever.add_documents([
        Document(id="auth", content="JWT authentication token bearer cookie security", metadata={}),
        Document(id="db", content="PostgreSQL database connection pool psycopg query", metadata={}),
        Document(id="docker", content="Docker container compose service nginx proxy", metadata={}),
    ])
    results = retriever.retrieve("JWT token authentication", k=3)
    assert results, "Should return at least one result"
    assert results[0].document.id == "auth"


def test_bm25_empty_corpus_returns_empty():
    retriever = InMemoryBM25Retriever()
    assert retriever.retrieve("anything", k=5) == []


def test_bm25_respects_k():
    retriever = InMemoryBM25Retriever()
    for i in range(10):
        retriever.add_documents([Document(id=f"d{i}", content=f"document about topic {i} keyword", metadata={})])
    results = retriever.retrieve("keyword topic", k=3)
    assert len(results) <= 3


def test_bm25_score_normalised():
    retriever = InMemoryBM25Retriever()
    retriever.add_documents([
        Document(id="a", content="python fastapi endpoint route handler", metadata={}),
        Document(id="b", content="sql database query insert update", metadata={}),
    ])
    results = retriever.retrieve("fastapi python", k=2)
    assert all(0.0 <= r.score <= 1.0 for r in results)


def test_bm25_clear_empties_index():
    retriever = InMemoryBM25Retriever()
    retriever.add_documents([Document(id="x", content="hello world", metadata={})])
    retriever.clear()
    assert retriever.retrieve("hello", k=1) == []


def test_bm25_no_match_returns_empty():
    retriever = InMemoryBM25Retriever()
    retriever.add_documents([Document(id="y", content="apple banana cherry", metadata={})])
    results = retriever.retrieve("xyz quantum physics", k=5)
    # BM25 scores 0 for no matching terms → filtered out
    assert results == []


# ---------------------------------------------------------------------------
# Hybrid / RRF tests
# ---------------------------------------------------------------------------

def _make_bm25_with_docs(docs: list[Document]) -> InMemoryBM25Retriever:
    r = InMemoryBM25Retriever()
    r.add_documents(docs)
    return r


def test_hybrid_deduplicates_results():
    docs = [
        Document(id="a", content="fastapi router endpoint async", metadata={}),
        Document(id="b", content="database orm sqlalchemy model", metadata={}),
        Document(id="c", content="docker compose service volumes", metadata={}),
    ]
    r1 = _make_bm25_with_docs(docs)
    r2 = _make_bm25_with_docs(docs)
    hybrid = HybridRetriever([r1, r2])
    results = hybrid.retrieve("fastapi endpoint", k=3)
    ids = [r.document.id for r in results]
    assert len(ids) == len(set(ids)), "Hybrid should deduplicate by doc key"


def test_hybrid_scores_are_normalised():
    docs = [Document(id=f"d{i}", content=f"content {i} keyword", metadata={}) for i in range(5)]
    r1 = _make_bm25_with_docs(docs)
    r2 = _make_bm25_with_docs(docs)
    hybrid = HybridRetriever([r1, r2])
    results = hybrid.retrieve("keyword content", k=3)
    assert all(0.0 <= r.score <= 1.0 for r in results)


def test_hybrid_single_retriever():
    docs = [Document(id="solo", content="single source of truth", metadata={})]
    r = _make_bm25_with_docs(docs)
    hybrid = HybridRetriever([r])
    results = hybrid.retrieve("truth", k=1)
    assert len(results) == 1


def test_hybrid_requires_at_least_one_retriever():
    with pytest.raises(ValueError):
        HybridRetriever([])


# ---------------------------------------------------------------------------
# create_retriever factory
# ---------------------------------------------------------------------------

def test_create_retriever_bm25():
    from src.rag import create_retriever
    r = create_retriever("bm25")
    assert r.name == "bm25_memory"


def test_create_retriever_unknown_raises():
    from src.rag import create_retriever
    with pytest.raises(ValueError, match="Unknown RAG strategy"):
        create_retriever("not_a_real_strategy")


def test_create_retriever_hybrid_no_pool():
    from src.rag import create_retriever
    # Hybrid with no pool defaults to in-memory (no DB needed)
    r = create_retriever("hybrid")
    assert r.name == "hybrid_rrf"


# ---------------------------------------------------------------------------
# PipelineIndexer context formatting
# ---------------------------------------------------------------------------

def test_format_context_empty():
    from src.rag.indexer import PipelineIndexer
    assert PipelineIndexer.format_context([]) == ""


def test_format_context_respects_max_chars():
    from src.rag.indexer import PipelineIndexer
    results = [
        RetrievalResult(
            document=Document(id=f"d{i}", content="x" * 1000, metadata={}),
            score=1.0,
            retriever="bm25",
        )
        for i in range(10)
    ]
    ctx = PipelineIndexer.format_context(results, max_chars=500)
    assert len(ctx) <= 600  # allow small header overhead


def test_format_context_includes_score_and_retriever():
    from src.rag.indexer import PipelineIndexer
    results = [
        RetrievalResult(
            document=Document(id="doc1", content="some useful text", metadata={"kind": "code"}),
            score=0.95,
            retriever="bm25",
        )
    ]
    ctx = PipelineIndexer.format_context(results)
    assert "0.95" in ctx
    assert "bm25" in ctx
    assert "some useful text" in ctx
