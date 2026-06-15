"""In-memory FAISS vector store shared by all tools within a single run.

Every tool writes its generated Markdown (and the user writes the initial
message) into the same ``VectorMemory``; later tools retrieve the most relevant
chunks from it during their reasoning step. The store lives for the duration of
one ``/agent/run`` request.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from .chunking import chunk_text
from .embeddings import EmbeddingProvider

log = logging.getLogger("agent_server.memory")


@dataclass
class MemoryRecord:
    text: str
    source: str   # tool key, or "user"
    role: str     # "user_message" | "tool_output" | "protocol"


class VectorMemory:
    def __init__(self, embeddings: EmbeddingProvider):
        self.embeddings = embeddings
        self._records: list[MemoryRecord] = []
        self._index = None  # lazily created so faiss is only needed when used

    def _ensure_index(self):
        if self._index is None:
            import faiss

            self._index = faiss.IndexFlatIP(self.embeddings.dim)
        return self._index

    def add(self, text: str, source: str, role: str, *, chunk: bool = True) -> int:
        """Chunk + embed + store ``text``. Returns the number of chunks added."""
        pieces = chunk_text(text) if chunk else [(text or "").strip()]
        pieces = [p for p in pieces if p.strip()]
        if not pieces:
            return 0
        vecs = self.embeddings.embed(pieces)
        index = self._ensure_index()
        index.add(np.ascontiguousarray(vecs))
        for p in pieces:
            self._records.append(MemoryRecord(p, source, role))
        log.info("    memory+ %d chunk(s) from %s/%s (total=%d)",
                 len(pieces), source, role, len(self._records))
        return len(pieces)

    def search(self, query: str, k: int = 4,
               exclude_source: str | None = None) -> list[tuple[float, MemoryRecord]]:
        """Return up to ``k`` (score, record) pairs most similar to ``query``."""
        if not self._records or not (query or "").strip():
            return []
        index = self._ensure_index()
        qv = self.embeddings.embed_one(query).reshape(1, -1)
        # Over-fetch so we can drop self-sourced hits and still return k.
        k2 = min(len(self._records), max(k * 3, k))
        scores, idxs = index.search(np.ascontiguousarray(qv), k2)
        out: list[tuple[float, MemoryRecord]] = []
        for score, idx in zip(scores[0], idxs[0]):
            if idx < 0:
                continue
            rec = self._records[int(idx)]
            if exclude_source is not None and rec.source == exclude_source:
                continue
            out.append((float(score), rec))
            if len(out) >= k:
                break
        return out

    def __len__(self) -> int:
        return len(self._records)
