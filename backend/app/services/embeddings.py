"""Embedding provider service supporting Google Gemini embeddings (gemini-embedding-001)

and deterministic fake embeddings for offline testing and development.
"""

from __future__ import annotations

import abc
import asyncio
import hashlib
import math
import random
from collections.abc import Sequence

import httpx

from app.core.config import settings
from app.core.logging import logger


def normalize_l2(vector: Sequence[float]) -> list[float]:
    """L2-normalize a vector so that cosine similarity equals dot product."""
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0.0:
        return list(vector)
    return [x / norm for x in vector]


class EmbeddingError(Exception):
    """Exception raised for errors during embedding generation."""


class EmbeddingProvider(abc.ABC):
    """Abstract interface for text embedding providers."""

    @abc.abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document texts with RETRIEVAL_DOCUMENT task type."""
        ...

    @abc.abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Embed a single search query text with RETRIEVAL_QUERY task type."""
        ...


class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic embedding provider for tests and local development without API keys."""

    def __init__(self, dimension: int = 768) -> None:
        self.dimension = dimension

    def _embed_single(self, text: str) -> list[float]:
        """Generate a deterministic unit vector from text hash."""
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)
        rng = random.Random(seed)
        vec = [rng.gauss(0.0, 1.0) for _ in range(self.dimension)]
        return normalize_l2(vec)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_single(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed_single(text)


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Google Gemini REST API embedding provider using batchEmbedContents."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        dimension: int | None = None,
        batch_size: int | None = None,
    ) -> None:
        self.api_key = api_key or settings.GEMINI_API_KEY
        if not self.api_key:
            raise EmbeddingError("GEMINI_API_KEY is not configured.")

        # Normalize model string e.g. "models/gemini-embedding-001"
        raw_model = model or settings.EMBEDDING_MODEL
        if not raw_model.startswith("models/"):
            self.model = f"models/{raw_model}"
        else:
            self.model = raw_model

        self.dimension = dimension or settings.EMBEDDING_DIM
        self.batch_size = batch_size or settings.EMBED_BATCH_SIZE

    async def _post_batch(
        self,
        requests_payload: list[dict],
        max_retries: int = 3,
    ) -> list[list[float]]:
        """Send a batchEmbedContents request with exponential backoff on 429/5xx."""
        url = f"https://generativelanguage.googleapis.com/v1beta/{self.model}:batchEmbedContents"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }
        body = {"requests": requests_payload}

        backoff = 1.0
        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt in range(max_retries + 1):
                try:
                    response = await client.post(url, headers=headers, json=body)
                    if response.status_code == 200:
                        data = response.json()
                        embeddings_data = data.get("embeddings", [])
                        results: list[list[float]] = []
                        for item in embeddings_data:
                            vals = item.get("values", [])
                            if len(vals) != self.dimension:
                                raise EmbeddingError(
                                    f"Dimension mismatch from Gemini embedding model: "
                                    f"expected {self.dimension}, got {len(vals)}"
                                )
                            # Normalize with L2 norm after MRL dimension reduction
                            results.append(normalize_l2(vals))
                        return results

                    if response.status_code in (401, 403):
                        raise EmbeddingError(
                            f"Authentication failed calling Gemini embedding API (HTTP {response.status_code}). Check GEMINI_API_KEY."
                        )

                    if response.status_code in (429, 500, 502, 503, 504):
                        retry_after_hdr = response.headers.get("Retry-After")
                        if retry_after_hdr:
                            try:
                                retry_wait = float(retry_after_hdr)
                            except ValueError:
                                retry_wait = backoff
                        else:
                            retry_wait = backoff

                        if attempt < max_retries:
                            logger.warning(
                                f"Gemini embedding API rate limit/error {response.status_code}, "
                                f"retrying in {retry_wait:.1f}s"
                            )
                            await asyncio.sleep(retry_wait)
                            backoff *= 2.0
                            continue
                        raise EmbeddingError(
                            f"Gemini embedding API failed with HTTP {response.status_code} after retries."
                        )

                    # Non-retryable error (e.g. 400) - do NOT leak API key in error
                    raise EmbeddingError(f"Gemini embedding API error HTTP {response.status_code}: {response.text}")
                except httpx.RequestError as exc:
                    if attempt < max_retries:
                        logger.warning(f"Network error calling Gemini embedding API, retrying in {backoff:.1f}s")
                        await asyncio.sleep(backoff)
                        backoff *= 2.0
                        continue
                    raise EmbeddingError(f"Network error calling Gemini embedding API: {type(exc).__name__}") from exc

        raise EmbeddingError("Exhausted retries calling Gemini embedding API.")

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed document texts in batches with RETRIEVAL_DOCUMENT and bounded concurrency."""
        if not texts:
            return []

        batches = [texts[i : i + self.batch_size] for i in range(0, len(texts), self.batch_size)]
        semaphore = asyncio.Semaphore(5)

        async def _embed_batch(b: list[str]) -> list[list[float]]:
            async with semaphore:
                payload = [
                    {
                        "model": self.model,
                        "content": {"parts": [{"text": t}]},
                        "taskType": "RETRIEVAL_DOCUMENT",
                        "outputDimensionality": self.dimension,
                    }
                    for t in b
                ]
                return await self._post_batch(payload)

        batch_results = await asyncio.gather(*[_embed_batch(b) for b in batches])
        all_embeddings: list[list[float]] = []
        for r in batch_results:
            all_embeddings.extend(r)
        return all_embeddings


    async def embed_query(self, text: str) -> list[float]:
        """Embed a search query with RETRIEVAL_QUERY task type."""
        payload = [
            {
                "model": self.model,
                "content": {"parts": [{"text": text}]},
                "taskType": "RETRIEVAL_QUERY",
                "outputDimensionality": self.dimension,
            }
        ]
        embeddings = await self._post_batch(payload)
        if not embeddings:
            raise EmbeddingError("No embedding returned for query.")
        return embeddings[0]


def get_embedding_provider() -> EmbeddingProvider:
    """Factory to get the configured embedding provider."""
    if settings.EMBEDDING_PROVIDER == "gemini" and settings.GEMINI_API_KEY:
        return GeminiEmbeddingProvider()
    if settings.EMBEDDING_PROVIDER == "gemini" and not settings.GEMINI_API_KEY:
        logger.warning("EMBEDDING_PROVIDER is 'gemini' but GEMINI_API_KEY is not set. Falling back to 'fake' provider.")
    return FakeEmbeddingProvider(dimension=settings.EMBEDDING_DIM)
