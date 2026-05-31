"""
Vector Store — hybrid search over text chunks.

Implements hybrid search combining:
    1. Dense Vector Search: pgvector (cosine similarity on OpenAI embeddings)
    2. Sparse Keyword Search: PostgreSQL full-text search (BM25-style via tsvector)

Applies Reciprocal Rank Fusion (RRF) to combine results at the DB level
or Python level. Supports strict metadata filtering before vector search.
"""

import logging
import uuid
from typing import Sequence, Any

from sqlalchemy.orm import Session
from sqlalchemy import text, select

from src.rag.models.database import RAGSectionChunk
from src.rag.models.schemas import MetadataFilter, ScoredChunk, ChunkMetadata
from src.rag.config import HYBRID_RETRIEVAL_TOP_K, RRF_K

logger = logging.getLogger("vittsarathi.rag.storage.vector_store")


class VectorStore:
    """
    Data access layer for hybrid vector search.
    """

    def __init__(self, db: Session):
        self.db = db

    def _build_metadata_filter_sql(self, filters: MetadataFilter) -> tuple[str, dict[str, Any]]:
        """
        Convert a MetadataFilter Pydantic model into PostgreSQL JSONB query logic
        and parameter bindings.
        """
        conditions = []
        params: dict[str, Any] = {}

        if filters.company_id:
            conditions.append("metadata->>'company_id' ILIKE :company_id")
            params["company_id"] = filters.company_id

        if filters.report_type:
            conditions.append("metadata->>'report_type' = :report_type")
            params["report_type"] = filters.report_type

        if filters.fiscal_year is not None:
            conditions.append("(metadata->>'fiscal_year')::int = :fiscal_year")
            params["fiscal_year"] = filters.fiscal_year
            
        if filters.fiscal_years:
            conditions.append("(metadata->>'fiscal_year')::int = ANY(:fiscal_years)")
            params["fiscal_years"] = filters.fiscal_years

        if filters.fiscal_quarter:
            conditions.append("metadata->>'fiscal_quarter' = :fiscal_quarter")
            params["fiscal_quarter"] = filters.fiscal_quarter

        if filters.section_types:
            conditions.append("metadata->>'section_type' = ANY(:section_types)")
            params["section_types"] = filters.section_types

        if filters.document_ids:
            conditions.append("metadata->>'document_id' = ANY(:document_ids)")
            params["document_ids"] = filters.document_ids

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        return where_clause, params

    async def search_dense(
        self,
        query_embedding: list[float],
        filters: MetadataFilter,
        top_k: int = HYBRID_RETRIEVAL_TOP_K,
    ) -> list[ScoredChunk]:
        """
        Perform a pure dense vector search using pgvector cosine similarity.
        """
        vector_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
        filter_sql, params = self._build_metadata_filter_sql(filters)
        
        # In pgvector, cosine distance is '<=>'. 
        # Similarity score = 1 - distance
        query = text(f"""
            SELECT 
                id, 
                chunk_text, 
                metadata, 
                (1 - (embedding <=> :vector)) AS score
            FROM rag_section_chunks
            WHERE {filter_sql}
            ORDER BY embedding <=> :vector
            LIMIT :limit
        """)
        
        params["vector"] = vector_str
        params["limit"] = top_k
        
        result = self.db.execute(query, params).fetchall()
        
        chunks = []
        for row in result:
            chunks.append(ScoredChunk(
                chunk_id=str(row.id),
                chunk_text=row.chunk_text,
                metadata=ChunkMetadata(**row.metadata),
                score=float(row.score),
                score_source="dense"
            ))
            
        return chunks

    async def search_sparse(
        self,
        query_text: str,
        filters: MetadataFilter,
        top_k: int = HYBRID_RETRIEVAL_TOP_K,
    ) -> list[ScoredChunk]:
        """
        Perform a pure sparse keyword search using PostgreSQL full-text search.
        """
        filter_sql, params = self._build_metadata_filter_sql(filters)
        
        # Convert user query to tsquery: 'revenue AND growth'
        # Basic parsing - replace spaces with &
        sanitized_query = query_text.replace("'", "''").strip()
        tsquery_terms = " & ".join([t for t in sanitized_query.split() if t.isalnum()])
        if not tsquery_terms:
            return []
            
        query = text(f"""
            SELECT 
                id, 
                chunk_text, 
                metadata, 
                ts_rank(fts_vector, to_tsquery('english', :tsquery)) AS score
            FROM rag_section_chunks
            WHERE {filter_sql}
              AND fts_vector @@ to_tsquery('english', :tsquery)
            ORDER BY score DESC
            LIMIT :limit
        """)
        
        params["tsquery"] = tsquery_terms
        params["limit"] = top_k
        
        result = self.db.execute(query, params).fetchall()
        
        chunks = []
        for row in result:
            chunks.append(ScoredChunk(
                chunk_id=str(row.id),
                chunk_text=row.chunk_text,
                metadata=ChunkMetadata(**row.metadata),
                score=float(row.score),
                score_source="sparse"
            ))
            
        return chunks

    async def hybrid_search(
        self,
        query_text: str,
        query_embedding: list[float],
        filters: MetadataFilter,
        top_k: int = HYBRID_RETRIEVAL_TOP_K,
        rrf_k: int = RRF_K,
    ) -> list[ScoredChunk]:
        """
        Perform hybrid search using both dense and sparse retrievers,
        and combine them using Reciprocal Rank Fusion (RRF).
        """
        logger.debug(f"Running hybrid search with filters: {filters}")
        
        # 1. Get results from both retrievers
        dense_results = await self.search_dense(query_embedding, filters, top_k=top_k)
        sparse_results = await self.search_sparse(query_text, filters, top_k=top_k)
        
        # 2. Combine and deduplicate chunks by ID
        chunk_map: dict[str, ScoredChunk] = {}
        
        for r in dense_results:
            chunk_map[r.chunk_id] = r
            
        for r in sparse_results:
            if r.chunk_id not in chunk_map:
                chunk_map[r.chunk_id] = r
                
        # 3. Apply Reciprocal Rank Fusion
        rrf_scores: dict[str, float] = {cid: 0.0 for cid in chunk_map.keys()}
        
        # Score dense ranks
        for rank, item in enumerate(dense_results):
            rrf_scores[item.chunk_id] += 1.0 / (rrf_k + rank + 1)
            
        # Score sparse ranks
        for rank, item in enumerate(sparse_results):
            rrf_scores[item.chunk_id] += 1.0 / (rrf_k + rank + 1)
            
        # 4. Sort by RRF score and apply new scores
        for cid, score in rrf_scores.items():
            chunk_map[cid].score = score
            chunk_map[cid].score_source = "hybrid_rrf"
            
        sorted_chunks = sorted(
            chunk_map.values(), 
            key=lambda x: x.score, 
            reverse=True
        )
        
        # 5. Return top_k fused results
        return sorted_chunks[:top_k]
