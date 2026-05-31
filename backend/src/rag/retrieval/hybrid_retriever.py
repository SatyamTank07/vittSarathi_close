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
from src.rag.retrieval.query_router import QueryRouter
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
    ):
        self.vector_store = vector_store
        self.pageindex_store = pageindex_store
        
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
        decision = await self.router.route_query(request)
        
        chunks: list[ScoredChunk] = []
        
        # 2. Execute retrieval strategy
        if decision.tier == QueryTier.T1_FACT_LOOKUP:
            chunks = await self._execute_tree_navigation(request, decision)
            
        elif decision.tier == QueryTier.T2_MULTI_SECTION:
            chunks = await self._execute_hybrid_search(request, decision)
            
        elif decision.tier == QueryTier.T3_CROSS_REFERENCE:
            chunks = await self._execute_hybrid_search(request, decision)
            # Ref resolution happens in context_assembler
            
        elif decision.tier == QueryTier.T4_TEMPORAL_SYNTHESIS:
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
        Since T1 queries are often looking for specific numbers in tables,
        we fetch the relevant PageIndex nodes and format them as chunks.
        """
        # If no specific document is requested, we can't reliably navigate the tree.
        # Fall back to hybrid search.
        filters = decision.metadata_filters
        
        if not filters.company_id or not filters.fiscal_year:
            logger.warning("Tree navigation requires company and year. Falling back to hybrid.")
            return await self._execute_hybrid_search(request, decision)
            
        # First, find the document ID matching the filters
        from src.rag.storage.document_store import DocumentStore
        doc_store = DocumentStore(self.vector_store.db)
        docs = doc_store.find_documents(
            company_id=filters.company_id,
            fiscal_year=filters.fiscal_year,
            fiscal_quarter=filters.fiscal_quarter
        )
        
        if not docs:
            logger.warning("No document found for tree navigation.")
            return []
            
        doc_id = docs[0].id
        
        # If section types are specified, fetch those nodes
        if filters.section_types:
            nodes = self.pageindex_store.find_nodes_by_type(doc_id, filters.section_types)
        else:
            # Otherwise, just fall back to hybrid search for general fact lookups
            return await self._execute_hybrid_search(request, decision)
            
        # Convert tree nodes into ScoredChunks for the reranker
        chunks = []
        for i, node in enumerate(nodes):
            if not node.tree_json:
                continue
                
            # Create a synthetic chunk text representing this structured node
            chunk_text = f"Structured Section: {node.node_title}\n"
            chunk_text += f"Summary: {node.tree_json.get('contextual_summary', '')}"
            
            metadata = ChunkMetadata(
                company_id=filters.company_id or "",
                report_type="annual", # Default, should extract from doc
                fiscal_year=filters.fiscal_year or 0,
                section_type=node.tree_json.get('section_type', 'unknown'),
                section_path=node.node_path,
                content_type="table",
                document_id=str(doc_id),
                section_id=str(node.section_id) if node.section_id else ""
            )
            
            chunks.append(ScoredChunk(
                chunk_id=str(node.id),
                chunk_text=chunk_text,
                metadata=metadata,
                score=1.0 - (i * 0.01), # Artificial descending score
                score_source="tree_navigation"
            ))
            
        return chunks
