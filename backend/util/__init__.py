"""Project-wide utilities for the Trial Agent backend.

Currently this package provides a small RAG (retrieval-augmented generation)
stack that lets the agent tools share a memory within a single run:

- ``embeddings``   : text -> vector (OpenAI in live mode, deterministic hashing
                     embedding in mock mode so it works without an API key).
- ``chunking``     : split user messages and tool-generated Markdown into chunks.
- ``vector_store`` : an in-memory FAISS store shared by every tool in one run.
- ``reasoning``    : a per-tool "reasoning" step that queries the store and
                     builds the context block injected into the tool's prompt.
"""

from .embeddings import EmbeddingProvider
from .chunking import chunk_text
from .vector_store import VectorMemory, MemoryRecord
from .reasoning import reason_before_tool, ReasoningResult, TOOL_FOCUS

__all__ = [
    "EmbeddingProvider",
    "chunk_text",
    "VectorMemory",
    "MemoryRecord",
    "reason_before_tool",
    "ReasoningResult",
    "TOOL_FOCUS",
]
