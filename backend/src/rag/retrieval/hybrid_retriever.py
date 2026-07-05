"""
Hybrid Retriever — orchestrates the full retrieval flow.

Combines the QueryRouter, EmbeddingService, VectorStore, PageIndexStore,
and CohereReranker to execute the optimal retrieval strategy based on
the user's query complexity (T1-T4).
"""

import logging
from typing import Sequence

from src.rag.models.schemas import (
    QueryRequest, 
    RetrievedContext, 
    RoutingDecision,
    QueryTier,
    ScoredChunk,
    ChunkMetadata
)
from src.rag.ingestion.embedding_service import EmbeddingService
from src.rag.retrieval.query_router import QueryRouter, log_routing_decision
from src.rag.retrieval.reranker import CohereReranker
from src.rag.storage.vector_store import VectorStore
from src.rag.storage.pageindex import PageIndexStore

logger = logging.getLogger("vittsarathi.rag.retrieval.hybrid_retriever")


class HybridRetriever:
    """
    Master orchestrator for the RAG retrieval phase.
    """

    def __init__(
        self,
        vector_store: VectorStore,
        pageindex_store: PageIndexStore,
        db_session=None,
    ):
        self.vector_store = vector_store
        self.pageindex_store = pageindex_store
        self.db_session = db_session
        
        # Initialize ML components
        self.router = QueryRouter()
        self.embedding_service = EmbeddingService()
        self.reranker = CohereReranker()

    async def retrieve(self, request: QueryRequest) -> RetrievedContext:
        """
        Execute the full retrieval pipeline.
        
        1. Route query (T1-T4)
        2. Execute strategy (Hybrid / Tree Navigation)
        3. Rerank
        4. Assemble Context
        """
        logger.info(f"Retrieving context for query: '{request.query}'")
        
        # 1. Route the query to determine strategy
        decision = await self.router.route_query(request, db_session=self.db_session)
        
        # ── Log classification decision ────────────
        if self.db_session is not None:
            log_routing_decision(
                db_session=self.db_session,
                query=request.query,
                decision=decision,
                fallback_reason=decision.explanation if decision.fallback_applied else None,
            )

        chunks: list[ScoredChunk] = []
        
        # 2. Execute retrieval strategy
        from src.rag.config import STRUCTURED_SECTION_TYPES
        
        # Check if the requested sections are primarily structured (PageIndex)
        filters = decision.metadata_filters
        is_structured_request = False
        if filters.section_types:
            is_structured_request = any(s in STRUCTURED_SECTION_TYPES for s in filters.section_types)
            
        if decision.tier == QueryTier.T1_FACT_LOOKUP:
            chunks = await self._execute_tree_navigation(request, decision)
            
        elif decision.tier == QueryTier.T2_MULTI_SECTION:
            # T2 is usually hybrid, but if they asked for structured data, navigate the tree
            if is_structured_request:
                chunks = await self._execute_tree_navigation(request, decision)
            else:
                chunks = await self._execute_hybrid_search(request, decision)
            
        elif decision.tier == QueryTier.T3_CROSS_REFERENCE:
            # T3 usually involves footnotes (structured data)
            if is_structured_request or not filters.section_types:
                chunks = await self._execute_tree_navigation(request, decision)
            else:
                chunks = await self._execute_hybrid_search(request, decision)
            
        elif decision.tier == QueryTier.T4_TEMPORAL_SYNTHESIS:
            # T4 could be comparing profits (structured) or MDA (narrative)
            if is_structured_request:
                chunks = await self._execute_tree_navigation(request, decision)
            else:
                chunks = await self._execute_hybrid_search(request, decision)
            
        else:
            # Fallback
            chunks = await self._execute_hybrid_search(request, decision)
            
        # 3. Rerank top results
        if chunks:
            chunks = await self.reranker.rerank(request.query, chunks)
            
        # 4. Context assembly is handled by a separate component that
        # this class will pass the raw chunks to.
        # For now, we return a basic RetrievedContext. The ContextAssembler
        # will enrich it with resolved references and token counts.
        
        return RetrievedContext(
            query=request.query,
            query_tier=decision.tier,
            chunks=chunks,
            retrieval_strategy=decision.retrieval_strategy,
            metadata_filters_applied=decision.metadata_filters.model_dump(exclude_none=True),
        )

    async def _execute_hybrid_search(
        self, request: QueryRequest, decision: RoutingDecision
    ) -> list[ScoredChunk]:
        """Execute BM25 + Dense vector search with RRF."""
        # Get query embedding
        query_embedding = await self.embedding_service.embed_query(request.query)
        
        # Run hybrid search (vector store handles RRF internally)
        chunks = await self.vector_store.hybrid_search(
            query_text=request.query,
            query_embedding=query_embedding,
            filters=decision.metadata_filters,
            top_k=50  # Fetch more candidates for the reranker
        )
        
        return chunks

    async def _execute_tree_navigation(
        self, request: QueryRequest, decision: RoutingDecision
    ) -> list[ScoredChunk]:
        """
        Execute tree navigation for structured data lookups.
        Since T1/T3/T4 queries often look for specific numbers in tables,
        we fetch the relevant PageIndex nodes and format them as chunks.
        """
        filters = decision.metadata_filters
        
        # We need a company, and at least one year
        has_year = filters.fiscal_year is not None or bool(filters.fiscal_years)
        if not filters.company_id or not has_year:
            logger.warning("Tree navigation requires company and year(s). Falling back to hybrid.")
            return await self._execute_hybrid_search(request, decision)
            
        # First, find the document IDs matching the filters
        from src.rag.storage.document_store import DocumentStore
        doc_store = DocumentStore(self.vector_store.db)
        docs = doc_store.find_documents(
            company_id=filters.company_id,
            fiscal_year=filters.fiscal_year,
            fiscal_years=filters.fiscal_years,
            fiscal_quarter=filters.fiscal_quarter
        )
        
        if not docs:
            logger.warning("No document found for tree navigation.")
            return []
            
        # For each document, find the requested section nodes
        chunks = []
        for doc in docs:
            if filters.section_types:
                nodes = self.pageindex_store.find_nodes_by_type(doc.id, filters.section_types)
            else:
                # If no specific section types, we can't pull the whole tree (too big).
                # Fall back to hybrid search for this query overall.
                return await self._execute_hybrid_search(request, decision)
                
            # Convert tree nodes into ScoredChunks for the reranker
            for i, node in enumerate(nodes):
                if not node.tree_json:
                    continue
                    
                # Create a synthetic chunk text representing this structured node
                chunk_text = f"Structured Section: {node.node_title}\n"
                chunk_text += f"Summary: {node.tree_json.get('contextual_summary', '')}\n"
                
                # We stringify the table for the LLM
                chunk_text += f"Data: {node.tree_json.get('data', {})}\n"
                
                # We package this as a ScoredChunk with perfect score (1.0)
                # because we know structurally this is EXACTLY what they asked for.
                meta = ChunkMetadata(
                    company_id=doc.company_id,
                    fiscal_year=doc.fiscal_year,
                    fiscal_quarter=doc.fiscal_quarter,
                    report_type=doc.report_type,
                    section_type=node.tree_json.get("section_type", "unknown"),
                    document_id=str(doc.id)
                )
                
                chunks.append(ScoredChunk(
                    chunk_id=str(node.id),
                    chunk_text=chunk_text,
                    metadata=meta,
                    score=1.0,
                    score_source="tree"
                ))
                
        return chunks
