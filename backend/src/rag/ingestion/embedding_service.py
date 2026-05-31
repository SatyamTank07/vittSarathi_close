"""
Embedding Service — batch embedding generation using OpenAI API.

Uses text-embedding-3-small (1536 dimensions) for cost-efficient,
high-quality embeddings. Handles batching (max 100 per request),
rate limiting with exponential backoff, and error recovery.
"""

import asyncio
import logging
import os
from typing import Any

from openai import AsyncOpenAI, RateLimitError, APIError

from src.rag.config import (
    EMBEDDING_MODEL,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_BATCH_SIZE,
)

logger = logging.getLogger("vittsarathi.rag.ingestion.embedding_service")


class EmbeddingService:
    """
    Generates vector embeddings for text chunks using the OpenAI API.

    Usage:
        service = EmbeddingService()
        vectors = await service.embed_batch(["text1", "text2", ...])
        single = await service.embed_single("some text")
    """

    def __init__(
        self,
        model: str = EMBEDDING_MODEL,
        dimensions: int = EMBEDDING_DIMENSIONS,
        batch_size: int = EMBEDDING_BATCH_SIZE,
    ):
        api_key = os.environ.get("OPENAI_API_KEY", "")
        api_key = api_key.strip('"').strip("'")

        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set.")

        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.dimensions = dimensions
        self.batch_size = batch_size

        # Retry config
        self._max_retries = 5
        self._base_delay = 1.0  # seconds

    async def embed_single(self, text: str) -> list[float]:
        """
        Embed a single text string.

        Args:
            text: The text to embed.

        Returns:
            List of floats (1536-dim vector).
        """
        if not text.strip():
            return [0.0] * self.dimensions

        results = await self._call_api([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of texts in batches of up to 100 (OpenAI limit).

        Handles:
            - Automatic batching for lists > 100
            - Rate limit retries with exponential backoff
            - Empty text handling (returns zero vectors)

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors, same order as input.
        """
        if not texts:
            return []

        # Pre-process: track empty texts (they get zero vectors)
        processed: list[tuple[int, str]] = []
        results: list[list[float] | None] = [None] * len(texts)

        for i, text in enumerate(texts):
            if text.strip():
                processed.append((i, text))
            else:
                results[i] = [0.0] * self.dimensions

        if not processed:
            return results  # type: ignore

        # Batch and embed
        total_batches = (len(processed) + self.batch_size - 1) // self.batch_size
        logger.info(
            f"Embedding {len(processed)} texts in {total_batches} batches "
            f"(model={self.model})"
        )

        for batch_idx in range(0, len(processed), self.batch_size):
            batch = processed[batch_idx : batch_idx + self.batch_size]
            batch_texts = [t for _, t in batch]
            batch_indices = [i for i, _ in batch]

            embeddings = await self._call_api(batch_texts)

            for idx, embedding in zip(batch_indices, embeddings):
                results[idx] = embedding

            batch_num = batch_idx // self.batch_size + 1
            if total_batches > 1:
                logger.info(f"  Batch {batch_num}/{total_batches} complete")

        # Safety check: fill any remaining None entries
        for i in range(len(results)):
            if results[i] is None:
                results[i] = [0.0] * self.dimensions

        return results  # type: ignore

    async def embed_query(self, query: str) -> list[float]:
        """
        Embed a search query. Alias for embed_single, but semantically
        distinct — queries may be processed differently in future models.

        Args:
            query: The search query text.

        Returns:
            Query embedding vector.
        """
        return await self.embed_single(query)

    # ─── Internal: API Call with Retry ──────────────────────

    async def _call_api(self, texts: list[str]) -> list[list[float]]:
        """
        Call the OpenAI embeddings API with retry and backoff.

        Args:
            texts: Batch of texts (max 100).

        Returns:
            List of embedding vectors.
        """
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            try:
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=texts,
                    dimensions=self.dimensions,
                )

                # Extract embeddings in order
                embeddings = [item.embedding for item in response.data]
                return embeddings

            except RateLimitError as e:
                last_error = e
                delay = self._base_delay * (2 ** attempt)
                logger.warning(
                    f"Rate limited (attempt {attempt + 1}/{self._max_retries}). "
                    f"Retrying in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)

            except APIError as e:
                last_error = e
                if e.status_code and e.status_code >= 500:
                    # Server error — retry
                    delay = self._base_delay * (2 ** attempt)
                    logger.warning(
                        f"API error {e.status_code} (attempt {attempt + 1}). "
                        f"Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    # Client error — don't retry
                    raise

            except Exception as e:
                last_error = e
                delay = self._base_delay * (2 ** attempt)
                logger.warning(
                    f"Unexpected error (attempt {attempt + 1}): {e}. "
                    f"Retrying in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Embedding API failed after {self._max_retries} retries: {last_error}"
        )
