from langchain_core.tools import tool
from typing import List
from src.core.database.connection import SessionLocal
from src.rag.models.schemas import QueryRequest, RoutingDecision, QueryTier, MetadataFilter, RetrievedContext
from src.rag.retrieval.hybrid_retriever import HybridRetriever
from src.rag.storage.vector_store import VectorStore
from src.rag.storage.pageindex import PageIndexStore
from src.rag.storage.ref_store import RefStore
from src.rag.storage.document_store import DocumentStore
from src.rag.retrieval.context_assembler import ContextAssembler
from src.tools.ticker_mapper import normalize_company_id

@tool
async def historical_trend_search(query: str, company_id: str, fiscal_years: List[int]) -> str:
    """
    Performs a multi-document search across several fiscal years. 
    Use this for temporal synthesis and Year-over-Year (YoY) comparisons to see how 
    a metric, strategy, or risk has changed over time.
    """
    db_company_id = normalize_company_id(company_id)
    with SessionLocal() as db:
        vector_store = VectorStore(db)
        page_index = PageIndexStore(db)
        ref_store = RefStore(db)
        doc_store = DocumentStore(db)
        
        request = QueryRequest(query=query)
        filters = MetadataFilter(
            company_id=db_company_id, 
            fiscal_years=fiscal_years
        )
        decision = RoutingDecision(
            tier=QueryTier.T4_TEMPORAL_SYNTHESIS, 
            metadata_filters=filters, 
            retrieval_strategy="vector_multi_doc", 
            explanation="Forced T4 Temporal lookup"
        )
        
        retriever = HybridRetriever(vector_store, page_index)
        chunks = await retriever._execute_hybrid_search(request, decision)
        
        if chunks:
            chunks = await retriever.reranker.rerank(query, chunks)
            
        ctx = RetrievedContext(
            query=request.query, 
            query_tier=QueryTier.T4_TEMPORAL_SYNTHESIS, 
            chunks=chunks, 
            retrieval_strategy="vector_multi_doc", 
            metadata_filters_applied=filters.model_dump(exclude_none=True)
        )
        
        assembler = ContextAssembler(ref_store, doc_store)
        final_ctx = assembler.assemble(ctx)
        
        output = []
        for c in final_ctx.chunks:
            output.append(f"--- Document: {c.metadata.fiscal_year} {c.metadata.section_type} ---\n{c.chunk_text}")
            
        return "\n\n".join(output) if output else "No historical data found."
