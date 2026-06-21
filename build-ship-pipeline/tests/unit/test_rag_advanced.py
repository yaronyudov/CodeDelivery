"""Tests for RAG guards, instrumentation, LLM-based retrievers, and recipes.

All LLM/DB interactions are faked — no network, no Postgres required.
"""
from __future__ import annotations

import pytest

from src.rag.base import Document, RetrievalResult, Retriever
from src.rag.guards import (
    MAX_K,
    MAX_QUERY_CHARS,
    RagInputError,
    validate_corpus,
    validate_k,
    validate_query,
)
from src.rag.instrument import InstrumentedRetriever

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeRetriever(Retriever):
    """Returns a fixed, query-independent result list (for composition tests)."""

    name = "fake"

    def __init__(self, results: dict[str, list[RetrievalResult]] | None = None) -> None:
        self.added: list[Document] = []
        self._results = results or {}
        self.cleared = False

    def add_documents(self, docs):
        self.added.extend(docs)

    def retrieve(self, query, k=5):
        if self._results:
            return self._results.get(query, [])[:k]
        # Default: echo a single doc whose content is the query
        return [RetrievalResult(Document(id="d", content=query), score=1.0, retriever=self.name)][:k]

    def clear(self):
        self.cleared = True


def _doc(doc_id: str, content: str = "x") -> Document:
    return Document(id=doc_id, content=content)


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def test_validate_query_rejects_empty():
    with pytest.raises(RagInputError) as exc:
        validate_query("   ")
    assert exc.value.reason == "empty_query"


def test_validate_query_rejects_too_long():
    with pytest.raises(RagInputError) as exc:
        validate_query("a" * (MAX_QUERY_CHARS + 1))
    assert exc.value.reason == "query_too_long"


def test_validate_query_passes_normal():
    assert validate_query("hello world") == "hello world"


def test_validate_k_clamps_to_max():
    assert validate_k(10_000) == MAX_K


def test_validate_k_rejects_zero():
    with pytest.raises(RagInputError):
        validate_k(0)


def test_validate_k_rejects_bool():
    # bool is a subclass of int — must be rejected explicitly
    with pytest.raises(RagInputError):
        validate_k(True)


def test_validate_corpus_allows_none():
    assert validate_corpus(None) is None


def test_validate_corpus_accepts_valid():
    assert validate_corpus("artifacts_v2") == "artifacts_v2"


@pytest.mark.parametrize("bad", ["Bad Corpus", "drop;table", "a" * 65, "UPPER"])
def test_validate_corpus_rejects_invalid(bad):
    with pytest.raises(RagInputError):
        validate_corpus(bad)


# ---------------------------------------------------------------------------
# InstrumentedRetriever
# ---------------------------------------------------------------------------

def test_instrumented_preserves_inner_name():
    inner = FakeRetriever()
    wrapped = InstrumentedRetriever(inner)
    assert wrapped.name == "fake"


def test_instrumented_passes_through_results():
    inner = FakeRetriever()
    wrapped = InstrumentedRetriever(inner)
    results = wrapped.retrieve("query text", k=3)
    assert len(results) == 1
    assert results[0].document.content == "query text"


def test_instrumented_enforces_query_validation():
    wrapped = InstrumentedRetriever(FakeRetriever())
    with pytest.raises(RagInputError):
        wrapped.retrieve("")


def test_instrumented_clamps_k():
    inner = FakeRetriever({"q": [
        RetrievalResult(_doc(f"d{i}"), score=1.0, retriever="fake") for i in range(200)
    ]})
    wrapped = InstrumentedRetriever(inner)
    results = wrapped.retrieve("q", k=10_000)  # clamped to MAX_K
    assert len(results) <= MAX_K


def test_instrumented_drops_oversize_docs():
    from src.rag.guards import MAX_DOC_CHARS
    inner = FakeRetriever()
    wrapped = InstrumentedRetriever(inner)
    wrapped.add_documents([
        _doc("small", "ok"),
        _doc("huge", "x" * (MAX_DOC_CHARS + 1)),
    ])
    added_ids = {d.id for d in inner.added}
    assert "small" in added_ids
    assert "huge" not in added_ids


def test_instrumented_clear_delegates():
    inner = FakeRetriever()
    InstrumentedRetriever(inner).clear()
    assert inner.cleared is True


# ---------------------------------------------------------------------------
# Multi-query (LLM expansion mocked)
# ---------------------------------------------------------------------------

def test_multi_query_merges_with_votes(monkeypatch):
    import src.rag.multi_query as mq

    monkeypatch.setattr(mq, "_expand_query", lambda *a, **k: ["variant one", "variant two"])

    # doc A appears for all 3 queries; doc B only for one → A should rank first
    shared = RetrievalResult(_doc("A", "shared"), score=0.5, retriever="fake")
    only_one = RetrievalResult(_doc("B", "rare"), score=0.9, retriever="fake")
    base = FakeRetriever({
        "original": [shared, only_one],
        "variant one": [shared],
        "variant two": [shared],
    })
    retriever = mq.MultiQueryRetriever(base_retriever=base, n_variants=2)
    results = retriever.retrieve("original", k=2)
    assert results[0].document.id == "A"  # 3 votes beats 1 vote


def test_multi_query_empty_when_nothing_found(monkeypatch):
    import src.rag.multi_query as mq
    monkeypatch.setattr(mq, "_expand_query", lambda *a, **k: [])
    base = FakeRetriever({"q": []})
    retriever = mq.MultiQueryRetriever(base_retriever=base)
    assert retriever.retrieve("q", k=5) == []


# ---------------------------------------------------------------------------
# Reranker (LLM scoring mocked)
# ---------------------------------------------------------------------------

def test_reranker_reorders_by_llm_score(monkeypatch):
    import src.rag.reranker as rr

    # Score "good" high, everything else low
    monkeypatch.setattr(
        rr, "_score_one",
        lambda query, content, *a, **k: 1.0 if "good" in content else 0.1,
    )
    reranker = rr.LLMReranker()
    candidates = [
        RetrievalResult(_doc("1", "irrelevant"), score=0.9, retriever="bm25"),
        RetrievalResult(_doc("2", "good match"), score=0.1, retriever="bm25"),
    ]
    out = reranker.rerank("query", candidates, k=2)
    assert out[0].document.id == "2"  # reranked to top despite low base score


def test_reranked_retriever_composes(monkeypatch):
    import src.rag.reranker as rr
    monkeypatch.setattr(rr, "_score_one", lambda *a, **k: 0.5)
    base = FakeRetriever({"q": [RetrievalResult(_doc("x", "c"), 0.2, "fake")]})
    composed = rr.RerankedRetriever(base=base, reranker=rr.LLMReranker(), fetch_k=10)
    results = composed.retrieve("q", k=5)
    assert len(results) == 1
    assert results[0].retriever == "reranker"


# ---------------------------------------------------------------------------
# Graph retriever (LLM extraction mocked)
# ---------------------------------------------------------------------------

def test_graph_bfs_finds_connected_docs(monkeypatch):
    import src.rag.graph as gr

    def fake_llm(system, user, *a, **k):
        if "Extract entities" in system:
            # auth.py defines login() which uses bcrypt
            return (
                '{"entities":[{"name":"auth.py","type":"file","description":""},'
                '{"name":"login","type":"function","description":""},'
                '{"name":"bcrypt","type":"technology","description":""}],'
                '"relations":[{"source":"auth.py","relation":"defines","target":"login"},'
                '{"source":"login","relation":"uses","target":"bcrypt"}]}'
            )
        # query entity extraction
        return '["bcrypt"]'

    monkeypatch.setattr(gr, "_llm_call", fake_llm)

    retriever = gr.InMemoryGraphRetriever(max_hops=2)
    retriever.add_documents([Document(id="auth", content="auth.py login bcrypt", metadata={})])

    # Query for bcrypt should reach auth.py via 2 hops (bcrypt→login→auth.py)
    results = retriever.retrieve("how is password hashing done", k=5)
    assert results, "graph should return the connected document"
    assert results[0].document.id == "auth"


def test_graph_empty_when_no_query_entities(monkeypatch):
    import src.rag.graph as gr
    monkeypatch.setattr(gr, "_llm_call", lambda system, user, *a, **k:
                        '{"entities":[],"relations":[]}' if "Extract" in system else "[]")
    retriever = gr.InMemoryGraphRetriever()
    retriever.add_documents([Document(id="d", content="text", metadata={})])
    assert retriever.retrieve("anything", k=5) == []


# ---------------------------------------------------------------------------
# Recipes (DB faked)
# ---------------------------------------------------------------------------

class FakeDB:
    def __init__(self, memory=None, knowledge=None):
        self._memory = memory or []
        self._knowledge = knowledge or []
        self.saved: list[dict] = []

    def list_memory(self, kinds=None):
        if kinds is None:
            return self._memory
        return [m for m in self._memory if m.get("kind") in kinds]

    def list_knowledge(self, run_id):
        return self._knowledge

    def save_memory(self, kind, key, value):
        self.saved.append({"kind": kind, "key": key, "value": value})


def test_retrieve_similar_plans_returns_context():
    from src.rag.recipes import retrieve_similar_plans
    db = FakeDB(memory=[
        {"kind": "past_plan", "key": "build a JWT auth service",
         "value": {"summary": "JWT auth with bcrypt", "tech_stack": ["fastapi", "jwt"]}},
        {"kind": "past_plan", "key": "build an ETL pipeline",
         "value": {"summary": "CSV to parquet", "tech_stack": ["pandas"]}},
    ])
    ctx = retrieve_similar_plans("I need JWT authentication", db, k=1)
    assert "Similar past plans" in ctx
    assert "JWT" in ctx


def test_retrieve_similar_plans_empty_db():
    from src.rag.recipes import retrieve_similar_plans
    assert retrieve_similar_plans("anything", FakeDB(memory=[]), k=3) == ""


def test_retrieve_similar_plans_none_db():
    from src.rag.recipes import retrieve_similar_plans
    assert retrieve_similar_plans("anything", None) == ""


def test_retrieve_debug_lessons():
    from src.rag.recipes import retrieve_debug_lessons
    db = FakeDB(memory=[
        {"kind": "lesson", "key": "k",
         "value": {"lessons": [{"message": "missing await caused timeout"}]}},
    ])
    ctx = retrieve_debug_lessons(["TimeoutError: await missing"], db, k=1)
    assert "Lessons from past similar failures" in ctx
    assert "await" in ctx


def test_retrieve_security_context_filters_topics():
    from src.rag.recipes import retrieve_security_context
    db = FakeDB(knowledge=[
        {"topic": "known_cves", "payload": {"cve": "CVE-2021-1234 SQL injection in login"}},
        {"topic": "codebase_map", "payload": {"map": "auth module handles login"}},
        {"topic": "irrelevant", "payload": {"x": "should be filtered out"}},
    ])
    ctx = retrieve_security_context("SQL injection login", db, run_id="run1", k=2)
    assert "security context" in ctx.lower()
    assert "CVE-2021-1234" in ctx


def test_persist_run_memory_writes_plan_and_lesson():
    from src.rag.recipes import persist_run_memory
    db = FakeDB()
    state = {
        "run_id": "r1",
        "feature_request": "build auth",
        "plan": {"summary": "JWT auth", "tech_stack": ["fastapi"], "tasks": []},
        "verdict": "minor",
        "findings": [
            {"agent": "security", "severity": "critical", "message": "hardcoded secret", "location": "x"},
            {"agent": "style", "severity": "info", "message": "nit", "location": "y"},
        ],
    }
    wrote = persist_run_memory(state, db)
    assert wrote is True
    kinds = {s["kind"] for s in db.saved}
    assert "past_plan" in kinds
    assert "lesson" in kinds
    # Only critical/major findings become lessons
    lesson = next(s for s in db.saved if s["kind"] == "lesson")
    assert len(lesson["value"]["lessons"]) == 1


def test_persist_run_memory_none_db():
    from src.rag.recipes import persist_run_memory
    assert persist_run_memory({"run_id": "r"}, None) is False


def test_recipe_swallows_db_errors():
    from src.rag.recipes import retrieve_similar_plans

    class BrokenDB:
        def list_memory(self, kinds=None):
            raise RuntimeError("db down")

    # Must degrade to "" rather than propagating
    assert retrieve_similar_plans("query", BrokenDB(), k=3) == ""
