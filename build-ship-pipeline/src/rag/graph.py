"""Graph RAG — entity-centric retrieval over a knowledge graph.

Algorithm
---------
Index phase (call index_documents()):
  1. For each document chunk, prompt an LLM to extract (entity, type, description)
     tuples and (source, relation, target) triples.
  2. Store entities in rag_entities and edges in rag_relations (DB-backed)
     OR in in-memory dicts (InMemoryGraphRetriever).

Query phase (call retrieve()):
  1. Extract query entities via a lightweight LLM call.
  2. Walk the graph: find neighbours (1–2 hops) of each query entity.
  3. Retrieve the document chunks that mention those entities.
  4. Return them ranked by number of matched entities.

Why graph RAG?
--------------
- Captures cross-file relationships (A imports B, service C calls service D).
- Surfaces relevant context even when keyword/embedding similarity is low.
- Particularly useful for the coder/reviewer agents which need to understand
  how pieces of the codebase connect.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from src.rag.base import Document, RetrievalResult, Retriever

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM helpers (reuse same litellm pattern as agents)
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM = """Extract entities and relationships from the following text.

Respond with a JSON object:
{
  "entities": [
    {"name": "...", "type": "file|function|class|service|concept|technology", "description": "..."}
  ],
  "relations": [
    {"source": "<entity name>",
     "relation": "imports|calls|inherits|uses|defines|depends_on",
     "target": "<entity name>"}
  ]
}

Be concise. Only extract clearly stated relationships. Respond ONLY with JSON."""

_QUERY_ENTITIES_SYSTEM = """Extract the key entities from this query for knowledge graph lookup.

Respond with a JSON array of entity names: ["EntityA", "EntityB", ...]

Respond ONLY with the JSON array."""


def _llm_call(system: str, user: str, model: str, api_key: str | None, api_base: str | None) -> str:
    import litellm

    litellm.suppress_debug_info = True
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": 1024,
    }
    if api_key:
        kwargs["api_key"] = api_key
    if api_base:
        kwargs["api_base"] = api_base
    try:
        resp = litellm.completion(**kwargs)
        return resp.choices[0].message.content or ""
    except Exception as exc:
        logger.warning("graph_rag LLM call failed: %s", exc)
        return ""


def _parse_json(text: str) -> Any:
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().strip("`").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# In-memory graph
# ---------------------------------------------------------------------------


@dataclass
class _Entity:
    name: str
    type: str
    description: str
    doc_ids: set[str] = field(default_factory=set)


class InMemoryGraphRetriever(Retriever):
    """Graph RAG backed by in-memory adjacency lists."""

    name = "graph_memory"

    def __init__(
        self,
        model: str = "anthropic/claude-haiku-4-5-20251001",
        api_key: str | None = None,
        api_base: str | None = None,
        max_hops: int = 2,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.api_base = api_base
        self.max_hops = max_hops
        self._entities: dict[str, _Entity] = {}  # name → Entity
        self._adj: dict[str, list[str]] = defaultdict(list)  # name → [neighbour names]
        self._docs: dict[str, Document] = {}  # id → Document

    def add_documents(self, docs: list[Document]) -> None:
        for doc in docs:
            self._docs[f"{doc.id}::{doc.chunk_index}"] = doc
            self._index_doc(doc)

    def _index_doc(self, doc: Document) -> None:
        raw = _llm_call(
            _EXTRACT_SYSTEM, doc.content[:2000], self.model, self.api_key, self.api_base
        )
        data = _parse_json(raw)
        if not data:
            return
        for ent in data.get("entities", []):
            name = ent.get("name", "").strip()
            if not name:
                continue
            if name not in self._entities:
                self._entities[name] = _Entity(
                    name=name,
                    type=ent.get("type", "concept"),
                    description=ent.get("description", ""),
                )
            self._entities[name].doc_ids.add(f"{doc.id}::{doc.chunk_index}")
        for rel in data.get("relations", []):
            src = rel.get("source", "").strip()
            tgt = rel.get("target", "").strip()
            if src and tgt:
                self._adj[src].append(tgt)
                self._adj[tgt].append(src)  # bidirectional for retrieval

    def _bfs(self, seeds: list[str], hops: int) -> set[str]:
        """Return all entity names reachable within *hops* from *seeds*."""
        visited: set[str] = set(seeds)
        frontier = list(seeds)
        for _ in range(hops):
            next_frontier: list[str] = []
            for name in frontier:
                for neighbour in self._adj.get(name, []):
                    if neighbour not in visited:
                        visited.add(neighbour)
                        next_frontier.append(neighbour)
            frontier = next_frontier
        return visited

    def retrieve(self, query: str, k: int = 5) -> list[RetrievalResult]:
        raw = _llm_call(_QUERY_ENTITIES_SYSTEM, query, self.model, self.api_key, self.api_base)
        parsed = _parse_json(raw)
        query_entities: list[str] = parsed if isinstance(parsed, list) else []

        if not query_entities:
            return []

        reachable = self._bfs(query_entities, self.max_hops)

        # Score docs by how many reachable entities mention them
        doc_hits: dict[str, int] = defaultdict(int)
        for entity_name in reachable:
            entity = self._entities.get(entity_name)
            if entity:
                for doc_key in entity.doc_ids:
                    doc_hits[doc_key] += 1

        ranked = sorted(doc_hits, key=lambda dk: doc_hits[dk], reverse=True)[:k]
        max_hits = doc_hits[ranked[0]] if ranked else 1

        return [
            RetrievalResult(
                document=self._docs[dk],
                score=doc_hits[dk] / max_hits,
                retriever=self.name,
            )
            for dk in ranked
            if dk in self._docs
        ]

    def clear(self) -> None:
        self._entities.clear()
        self._adj.clear()
        self._docs.clear()


# ---------------------------------------------------------------------------
# DB-backed graph (rag_entities + rag_relations tables)
# ---------------------------------------------------------------------------


class PostgresGraphRetriever(Retriever):
    """Graph RAG backed by rag_entities + rag_relations DB tables."""

    name = "graph_postgres"

    def __init__(
        self,
        pool: Any,
        model: str = "anthropic/claude-haiku-4-5-20251001",
        api_key: str | None = None,
        api_base: str | None = None,
        corpus: str = "custom",
        run_id: str | None = None,
        max_hops: int = 2,
    ) -> None:
        self._pool = pool
        self.model = model
        self.api_key = api_key
        self.api_base = api_base
        self._corpus = corpus
        self._run_id = run_id
        self.max_hops = max_hops

    def add_documents(self, docs: list[Document]) -> None:
        for doc in docs:
            self._index_doc(doc)

    def _index_doc(self, doc: Document) -> None:
        raw = _llm_call(
            _EXTRACT_SYSTEM, doc.content[:2000], self.model, self.api_key, self.api_base
        )
        data = _parse_json(raw)
        if not data:
            return

        entity_ids: dict[str, int] = {}
        with self._pool.connection() as conn:
            for ent in data.get("entities", []):
                name = ent.get("name", "").strip()
                if not name:
                    continue
                row = conn.execute(
                    """INSERT INTO rag_entities (corpus, run_id, name, type, description,
                       attributes)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (corpus, name) DO NOTHING RETURNING id""",
                    (
                        self._corpus,
                        self._run_id,
                        name,
                        ent.get("type", "concept"),
                        ent.get("description", ""),
                        json.dumps({"doc_id": doc.id}),
                    ),
                ).fetchone()
                if row:
                    entity_ids[name] = row[0]
                else:
                    existing = conn.execute(
                        "SELECT id FROM rag_entities WHERE corpus=%s AND name=%s",
                        (self._corpus, name),
                    ).fetchone()
                    if existing:
                        entity_ids[name] = existing[0]

            for rel in data.get("relations", []):
                src, tgt = rel.get("source", "").strip(), rel.get("target", "").strip()
                relation = rel.get("relation", "uses")
                if src in entity_ids and tgt in entity_ids:
                    conn.execute(
                        """INSERT INTO rag_relations (source_id, target_id, relation)
                           VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
                        (entity_ids[src], entity_ids[tgt], relation),
                    )

    def retrieve(self, query: str, k: int = 5) -> list[RetrievalResult]:
        raw = _llm_call(_QUERY_ENTITIES_SYSTEM, query, self.model, self.api_key, self.api_base)
        query_entities: list[str] = _parse_json(raw) or []
        if not query_entities:
            return []

        with self._pool.connection() as conn:
            placeholders = ",".join(["%s"] * len(query_entities))
            seeds = conn.execute(
                f"SELECT id, name FROM rag_entities WHERE corpus=%s AND name IN ({placeholders})",
                [self._corpus] + query_entities,
            ).fetchall()
            if not seeds:
                return []
            seed_ids = [r[0] for r in seeds]

            # BFS for max_hops via SQL CTE
            hop_sql = """
                WITH RECURSIVE graph(id, depth) AS (
                    SELECT unnest(%s::bigint[]), 0
                    UNION
                    SELECT CASE WHEN r.source_id = g.id THEN r.target_id ELSE r.source_id END,
                           g.depth + 1
                    FROM graph g
                    JOIN rag_relations r ON (r.source_id = g.id OR r.target_id = g.id)
                    WHERE g.depth < %s
                )
                SELECT DISTINCT id FROM graph
            """
            reachable_rows = conn.execute(hop_sql, (seed_ids, self.max_hops)).fetchall()
            reachable_ids = [r[0] for r in reachable_rows]

            attr_rows = conn.execute(
                "SELECT attributes FROM rag_entities"
                f" WHERE id IN ({','.join(['%s'] * len(reachable_ids))})",
                reachable_ids,
            ).fetchall()

        doc_id_hits: dict[str, int] = defaultdict(int)
        for (attrs,) in attr_rows:
            did = (attrs or {}).get("doc_id")
            if did:
                doc_id_hits[did] += 1

        # Fetch corresponding rag_documents
        top_doc_ids = sorted(doc_id_hits, key=lambda d: doc_id_hits[d], reverse=True)[:k]
        if not top_doc_ids:
            return []

        from psycopg.rows import dict_row

        with self._pool.connection() as conn:
            placeholders = ",".join(["%s"] * len(top_doc_ids))
            rows = conn.execute(
                "SELECT doc_id, chunk_index, content, metadata FROM rag_documents"
                f" WHERE doc_id IN ({placeholders}) LIMIT %s",
                top_doc_ids + [k],
                row_factory=dict_row,
            ).fetchall()

        max_hits = max(doc_id_hits.values(), default=1)
        return [
            RetrievalResult(
                document=Document(
                    id=r["doc_id"],
                    content=r["content"],
                    metadata=r["metadata"] or {},
                    chunk_index=r["chunk_index"],
                ),
                score=doc_id_hits.get(r["doc_id"], 0) / max_hits,
                retriever=self.name,
            )
            for r in rows
        ]

    def clear(self) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "DELETE FROM rag_entities WHERE corpus=%s AND (%s IS NULL OR run_id=%s)",
                (self._corpus, self._run_id, self._run_id),
            )
