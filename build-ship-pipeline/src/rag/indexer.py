"""Pipeline-aware document indexer.

Converts the pipeline's three native data sources into RAG Document chunks:

  artifacts  — generated code, tests, compose files (from rag_documents via DB)
  knowledge  — shared knowledge base entries (from knowledge table)
  memory     — long-term cross-run memory (from memory table)

Usage inside an agent or at run start
--------------------------------------
    from src.rag.indexer import PipelineIndexer
    from src.rag import create_retriever

    retriever = create_retriever("hybrid")
    indexer = PipelineIndexer(retriever)
    indexer.index_state(state, db)           # index current run
    indexer.index_memory(db, kinds=["pattern"])  # index cross-run memory

    results = retriever.retrieve("JWT authentication", k=5)
    context = indexer.format_context(results)  # ready to append to a prompt
"""
from __future__ import annotations

import json
import logging

from src.rag.base import Retriever
from src.rag.chunker import RecursiveChunker

logger = logging.getLogger(__name__)

_DEFAULT_CHUNKER = RecursiveChunker(target_size=512, overlap=64)


class PipelineIndexer:
    """Index pipeline state and DB data sources into a retriever."""

    def __init__(
        self,
        retriever: Retriever,
        chunker: RecursiveChunker | None = None,
    ) -> None:
        self._retriever = retriever
        self._chunker = chunker or _DEFAULT_CHUNKER

    # ------------------------------------------------------------------
    # Indexing helpers
    # ------------------------------------------------------------------

    def index_state(self, state: dict, db) -> None:
        """Index artifacts and plan from the current PipelineState."""
        self._index_plan(state)
        self._index_artifacts(state, db)

    def _index_plan(self, state: dict) -> None:
        plan = state.get("plan", {})
        if not plan:
            return
        run_id = state.get("run_id", "unknown")
        text = json.dumps(plan, indent=2)
        docs = self._chunker.chunk(
            doc_id=f"plan:{run_id}",
            content=text,
            metadata={"kind": "plan", "run_id": run_id},
        )
        self._retriever.add_documents(docs)
        logger.debug("indexed plan for run %s (%d chunks)", run_id, len(docs))

    def _index_artifacts(self, state: dict, db) -> None:
        run_id = state.get("run_id", "unknown")
        for artifact in state.get("artifacts", []):
            content_ref = artifact.get("content_ref")
            if not content_ref:
                continue
            try:
                content = db.load_artifact(content_ref)
            except Exception:
                continue
            if not content:
                continue
            docs = self._chunker.chunk(
                doc_id=f"artifact:{content_ref}",
                content=content,
                metadata={
                    "kind": artifact.get("kind", "code"),
                    "path": artifact.get("path", ""),
                    "run_id": run_id,
                },
            )
            self._retriever.add_documents(docs)
        logger.debug("indexed artifacts for run %s", run_id)

    def index_knowledge(self, db, run_id: str) -> None:
        """Index all knowledge-base entries for *run_id*."""
        try:
            rows = db.list_knowledge(run_id)
        except Exception:
            rows = []
        for row in rows:
            payload_text = json.dumps(row.get("payload", {}), indent=2)
            docs = self._chunker.chunk(
                doc_id=f"knowledge:{run_id}:{row.get('topic','')}",
                content=payload_text,
                metadata={"kind": "knowledge", "topic": row.get("topic", ""), "run_id": run_id},
            )
            self._retriever.add_documents(docs)
        logger.debug("indexed %d knowledge entries for run %s", len(rows), run_id)

    def index_memory(self, db, kinds: list[str] | None = None) -> None:
        """Index long-term memory entries (patterns, lessons, past plans)."""
        try:
            rows = db.list_memory(kinds=kinds)
        except Exception:
            rows = []
        for row in rows:
            value_text = json.dumps(row.get("value", {}), indent=2)
            docs = self._chunker.chunk(
                doc_id=f"memory:{row.get('kind','')}:{row.get('key','')}",
                content=value_text,
                metadata={"kind": row.get("kind", ""), "key": row.get("key", "")},
            )
            self._retriever.add_documents(docs)
        logger.debug("indexed %d memory entries", len(rows))

    # ------------------------------------------------------------------
    # Context formatting
    # ------------------------------------------------------------------

    @staticmethod
    def format_context(results: list, max_chars: int = 4000) -> str:
        """Format retrieval results into a string ready to inject into a prompt."""
        if not results:
            return ""
        lines: list[str] = ["## Retrieved context\n"]
        total = 0
        for i, res in enumerate(results, start=1):
            doc = res.document
            meta_parts = []
            if doc.metadata.get("path"):
                meta_parts.append(f"path={doc.metadata['path']}")
            if doc.metadata.get("kind"):
                meta_parts.append(f"kind={doc.metadata['kind']}")
            meta = ", ".join(meta_parts)
            header = f"[{i}] score={res.score:.2f} retriever={res.retriever}"
            if meta:
                header += f" ({meta})"
            entry = f"{header}\n{doc.content}\n"
            if total + len(entry) > max_chars:
                break
            lines.append(entry)
            total += len(entry)
        return "\n".join(lines)
