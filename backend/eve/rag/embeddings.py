"""Embedding engine supporting Gemini (cloud), Ollama (local), and deterministic fallback."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import httpx
import numpy as np

from eve.config import Settings

log = logging.getLogger(__name__)

EMBEDDING_DIM = 768


def _hash_fallback_embedding(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Deterministic, normalized pseudo-embedding for testing or air-gapped fallback."""
    vec = np.zeros(dim, dtype=np.float32)
    words = text.lower().split()
    if not words:
        vec[0] = 1.0
        return vec.tolist()

    for word in words:
        # Hash word into multiple pseudo-random buckets
        h = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 16) % 2 == 0 else -1.0
        vec[idx] += sign

    norm = float(np.linalg.norm(vec))
    if norm > 1e-9:
        vec = vec / norm
    else:
        vec[0] = 1.0
    return vec.tolist()


class EmbeddingEngine:
    """Multi-tier text embedding provider."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._gemini_client: Any = None
        self._init_gemini()

    def _init_gemini(self) -> None:
        key = self.settings.resolved_gemini_api_key
        if key:
            try:
                from google import genai

                self._gemini_client = genai.Client(api_key=key)
            except Exception as exc:  # noqa: BLE001
                log.warning("Failed to initialize Google GenAI embedding client: %s", exc)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Compute 768-dimensional normalized embeddings for a batch of strings."""
        if not texts:
            return []

        # 1. Try Gemini cloud embedding
        if self._gemini_client is not None:
            try:
                resp = self._gemini_client.models.embed_content(
                    model=self.settings.embedding_model,
                    contents=texts,
                )
                if resp.embeddings:
                    results: list[list[float]] = []
                    for emb in resp.embeddings:
                        vals = list(emb.values)
                        # Pad or truncate if dimension differs
                        if len(vals) < EMBEDDING_DIM:
                            vals.extend([0.0] * (EMBEDDING_DIM - len(vals)))
                        elif len(vals) > EMBEDDING_DIM:
                            vals = vals[:EMBEDDING_DIM]
                        results.append(vals)
                    return results
            except Exception as exc:  # noqa: BLE001
                log.warning("Gemini embedding failed (%s); trying Ollama...", exc)

        # 2. Try Ollama local embedding
        try:
            url = f"{self.settings.ollama_base_url.rstrip('/')}/api/embed"
            with httpx.Client(timeout=10.0) as client:
                res = client.post(
                    url,
                    json={
                        "model": self.settings.ollama_embedding_model,
                        "input": texts,
                    },
                )
                if res.status_code == 200:
                    data = res.json()
                    raw_embs = data.get("embeddings") or []
                    if raw_embs:
                        results = []
                        for emb in raw_embs:
                            vals = list(emb)
                            if len(vals) < EMBEDDING_DIM:
                                vals.extend([0.0] * (EMBEDDING_DIM - len(vals)))
                            elif len(vals) > EMBEDDING_DIM:
                                vals = vals[:EMBEDDING_DIM]
                            results.append(vals)
                        return results
        except Exception as exc:  # noqa: BLE001
            log.debug("Ollama embedding failed (%s); falling back to deterministic projection", exc)

        # 3. Deterministic normalized hash fallback
        return [_hash_fallback_embedding(t, EMBEDDING_DIM) for t in texts]

    def embed_query(self, query: str) -> list[float]:
        """Compute embedding for a single search query."""
        results = self.embed_texts([query])
        return results[0] if results else _hash_fallback_embedding(query, EMBEDDING_DIM)
