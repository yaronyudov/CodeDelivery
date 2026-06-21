"""Core types shared across all RAG retrievers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Document:
    """A single retrievable unit of text."""

    id: str  # stable source document identifier
    content: str  # text content of this chunk
    metadata: dict[str, Any] = field(default_factory=dict)
    chunk_index: int = 0  # position within the source document


@dataclass
class RetrievalResult:
    document: Document
    score: float  # higher = more relevant (normalised to 0–1 where possible)
    retriever: str  # which strategy produced this result


class Retriever:
    """Abstract base class all retrievers must implement."""

    name: str = "base"

    def add_documents(self, docs: list[Document]) -> None:
        """Index a list of documents into the retriever's backing store."""
        raise NotImplementedError

    def retrieve(self, query: str, k: int = 5) -> list[RetrievalResult]:
        """Return up to *k* results ranked by relevance to *query*."""
        raise NotImplementedError

    def clear(self) -> None:
        """Remove all indexed documents."""
