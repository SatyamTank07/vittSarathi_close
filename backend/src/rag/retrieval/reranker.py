"""
Cohere Reranker — refines and reorders search results.

Uses the Cohere Rerank v3 API to reorder chunks returned by the hybrid
retriever based on their true semantic relevance to the query. This is
critical for overcoming the limitations of both BM25 and standard vector embeddings.
"""

import logging
import os

import httpx

from src.rag.config import (
    COHERE_API_KEY,
    COHERE_RERANK_MODEL,
    RERANKER_TOP_K,
)
from src.rag.models.schemas import ScoredChunk

logger = logging.getLogger("vittsarathi.rag.retrieval.reranker")


class CohereReranker:
    """
    Reranks search results using the Cohere Rerank API.

    Usage:
        reranker = CohereReranker()
        reranked = await reranker.rerank(query, candidate_chunks)
    """

    def __init__(self, top_n: int = RERANKER_TOP_K):
        self.api_key = COHERE_API_KEY
        if not self.api_key:
            logger.warning(
                "COHERE_API_KEY not set. Reranking will be a pass-through."
            )

        self.model = COHERE_RERANK_MODEL
        self.top_n = top_n
        self.url = "https://api.cohere.com/v1/rerank"

    async def rerank(
        self, query: str, chunks: list[ScoredChunk]
    ) -> list[ScoredChunk]:
        """
        Rerank a list of ScoredChunks based on their relevance to the query.

        Args:
            query: The user query.
            chunks: Candidate chunks from the hybrid retriever.

        Returns:
            List of ScoredChunk, reordered and truncated to top_n.
        """
        if not chunks:
            return []

        if not self.api_key:
            # Fallback if no API key is configured
            return sorted(chunks, key=lambda x: x.score, reverse=True)[:self.top_n]

        # Extract text for the API call
        documents = [c.chunk_text for c in chunks]

        payload = {
            "model": self.model,
            "query": query,
            "documents": documents,
            "top_n": self.top_n,
            "return_documents": False,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }

        logger.debug(f"Reranking {len(chunks)} chunks via Cohere")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.url, headers=headers, json=payload
                )

            if response.status_code != 200:
                logger.error(f"Cohere API error {response.status_code}: {response.text}")
                # Fallback to original order
                return sorted(chunks, key=lambda x: x.score, reverse=True)[:self.top_n]

            data = response.json()
            results = data.get("results", [])

            # Apply new scores and order
            reranked_chunks: list[ScoredChunk] = []
            
            for result in results:
                original_idx = result["index"]
                relevance_score = result["relevance_score"]
                
                chunk = chunks[original_idx]
                chunk.score = relevance_score
                chunk.score_source = "cohere_reranker"
                reranked_chunks.append(chunk)

            return reranked_chunks

        except Exception as e:
            logger.error(f"Cohere reranking failed: {e}")
            # Fallback to original order
            return sorted(chunks, key=lambda x: x.score, reverse=True)[:self.top_n]
