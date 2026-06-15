"""Text embedding provider with a live (OpenAI) and a mock backend.

The mock backend is a deterministic hashing bag-of-words embedding so the whole
RAG pipeline (chunking -> FAISS -> retrieval) works end-to-end without an API
key. In live mode it calls OpenAI ``text-embedding-3-small``.
"""

from __future__ import annotations

import hashlib
import logging
import re

import numpy as np

log = logging.getLogger("agent_server.embeddings")

_TOKEN_RE = re.compile(r"[a-zA-Z0-9\uac00-\ud7a3]+")

# text-embedding-3-small dimensionality.
_OPENAI_DIM = 1536


def _normalize(vecs: np.ndarray) -> np.ndarray:
    """L2-normalize rows so inner product == cosine similarity."""
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (vecs / norms).astype("float32")


class EmbeddingProvider:
    def __init__(self, mock: bool, model: str = "text-embedding-3-small", mock_dim: int = 384):
        self.mock = mock
        self.model = model
        self.mock_dim = mock_dim
        self._client = None

    @property
    def dim(self) -> int:
        return self.mock_dim if self.mock else _OPENAI_DIM

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (n, dim) float32 matrix of unit-norm embeddings."""
        if not texts:
            return np.zeros((0, self.dim), dtype="float32")
        if self.mock:
            vecs = np.stack([self._hash_embed(t) for t in texts])
        else:
            vecs = self._openai_embed(texts)
        return _normalize(vecs)

    def embed_one(self, text: str) -> np.ndarray:
        return self.embed([text])[0]

    # -- backends -----------------------------------------------------------
    def _hash_embed(self, text: str) -> np.ndarray:
        """Signed hashing trick: deterministic, no network, decent for demos."""
        vec = np.zeros(self.mock_dim, dtype="float32")
        for tok in _TOKEN_RE.findall((text or "").lower()):
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            idx = h % self.mock_dim
            sign = 1.0 if (h >> 9) & 1 else -1.0
            vec[idx] += sign
        return vec

    def _openai_embed(self, texts: list[str]) -> np.ndarray:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI()
        resp = self._client.embeddings.create(model=self.model, input=texts)
        return np.array([d.embedding for d in resp.data], dtype="float32")
