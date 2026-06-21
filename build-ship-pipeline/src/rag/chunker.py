"""Document chunking strategies.

Chunks are the unit of retrieval — smaller = more precise recall,
larger = more context per result.  Three strategies are provided:

- FixedChunker      — splits on character count with configurable overlap
- SentenceChunker   — splits on sentence boundaries (. ! ?) with overlap
- RecursiveChunker  — tries paragraph → line → word splits until target size
                      (mirrors LangChain RecursiveCharacterTextSplitter)
"""
from __future__ import annotations

import re

from src.rag.base import Document


class FixedChunker:
    """Split text into fixed-size character chunks with overlap."""

    def __init__(self, chunk_size: int = 512, overlap: int = 64) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, doc_id: str, content: str, metadata: dict | None = None) -> list[Document]:
        meta = metadata or {}
        chunks: list[Document] = []
        start = 0
        idx = 0
        while start < len(content):
            end = min(start + self.chunk_size, len(content))
            chunks.append(Document(id=doc_id, content=content[start:end], metadata=meta, chunk_index=idx))
            if end == len(content):
                break
            start = end - self.overlap
            idx += 1
        return chunks


class SentenceChunker:
    """Split text on sentence boundaries, grouping up to *max_sentences* per chunk."""

    _BOUNDARY = re.compile(r"(?<=[.!?])\s+")

    def __init__(self, max_sentences: int = 5, overlap_sentences: int = 1) -> None:
        self.max_sentences = max_sentences
        self.overlap = overlap_sentences

    def chunk(self, doc_id: str, content: str, metadata: dict | None = None) -> list[Document]:
        meta = metadata or {}
        sentences = self._BOUNDARY.split(content.strip())
        if not sentences:
            return []
        chunks: list[Document] = []
        idx = 0
        i = 0
        while i < len(sentences):
            window = sentences[i: i + self.max_sentences]
            chunks.append(Document(id=doc_id, content=" ".join(window), metadata=meta, chunk_index=idx))
            i += max(1, self.max_sentences - self.overlap)
            idx += 1
        return chunks


class RecursiveChunker:
    """Recursive splitting: tries paragraph → line → space until target_size is met.

    Mirrors LangChain's RecursiveCharacterTextSplitter behaviour.
    """

    _SEPS = ["\n\n", "\n", ". ", " ", ""]

    def __init__(self, target_size: int = 512, overlap: int = 64) -> None:
        self.target_size = target_size
        self.overlap = overlap

    def chunk(self, doc_id: str, content: str, metadata: dict | None = None) -> list[Document]:
        meta = metadata or {}
        raw_chunks = self._split(content)
        docs: list[Document] = []
        for i, text in enumerate(raw_chunks):
            docs.append(Document(id=doc_id, content=text, metadata=meta, chunk_index=i))
        return docs

    def _split(self, text: str) -> list[str]:
        if len(text) <= self.target_size:
            return [text] if text.strip() else []

        for sep in self._SEPS:
            parts = text.split(sep) if sep else list(text)
            if len(parts) > 1:
                return self._merge(parts, sep)

        return [text]  # unsplittable single token/word

    def _merge(self, parts: list[str], sep: str) -> list[str]:
        chunks: list[str] = []
        current = ""
        for part in parts:
            candidate = (current + sep + part) if current else part
            if len(candidate) <= self.target_size:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                # Sub-split oversized part
                if len(part) > self.target_size:
                    chunks.extend(self._split(part))
                    current = ""
                else:
                    current = part
        if current:
            chunks.append(current)
        # Apply overlap: prepend tail of previous chunk
        if self.overlap > 0 and len(chunks) > 1:
            overlapped: list[str] = [chunks[0]]
            for i in range(1, len(chunks)):
                tail = chunks[i - 1][-self.overlap:]
                overlapped.append(tail + chunks[i])
            return overlapped
        return chunks
