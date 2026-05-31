from langchain_core.tools import tool
from src.core.database.connection import SessionLocal
from src.rag.models.schemas import QueryRequest, RoutingDecision, QueryTier, MetadataFilter, RetrievedContext
from src.rag.retrieval.hybrid_retriever import HybridRetriever
from src.rag.storage.vector_store import VectorStore
from src.rag.storage.pageindex import PageIndexStore
from src.rag.storage.ref_store import RefStore
from src.rag.storage.document_store import DocumentStore
from src.rag.retrieval.context_assembler import ContextAssembler

@tool
async def deep_dive_cross_ref(query: str, company_id: str, fiscal_year: int) -> str:
    """
    Searches for a specific financial line item (e.g. 'Long Term Debt' or 'Revenue') and 
    automatically retrieves its associated footnote from the 'Notes to Accounts'.
    Use this when you need to explain how a number was calculated or find the exact breakdown 
    of a line item that references a Note.
    """
    with SessionLocal() as db:
        vector_store = VectorStore(db)
        page_index = PageIndexStore(db)
        ref_store = RefStore(db)
        doc_store = DocumentStore(db)
        
        request = QueryRequest(query=query)
        filters = MetadataFilter(
            company_id=company_id, 
            fiscal_year=fiscal_year
        )
        # Force T3 so the context assembler explicitly runs reference resolution
        decision = RoutingDecision(
            tier=QueryTier.T3_CROSS_REFERENCE, 
            metadata_filters=filters, 
            retrieval_strategy="hybrid", 
            explanation="Forced T3 Cross-Ref lookup"
        )
        
        retriever = HybridRetriever(vector_store, page_index)
        chunks = await retriever._execute_hybrid_search(request, decision)
        
        if chunks:
            chunks = await retriever.reranker.rerank(query, chunks)
            
        ctx = RetrievedContext(
            query=request.query, 
            query_tier=QueryTier.T3_CROSS_REFERENCE, 
            chunks=chunks, 
            retrieval_strategy="hybrid", 
            metadata_filters_applied=filters.model_dump(exclude_none=True)
        )
        
        assembler = ContextAssembler(ref_store, doc_store)
        final_ctx = assembler.assemble(ctx)
        
        output = []
        for c in final_ctx.chunks:
            output.append(f"--- Context: {c.metadata.section_type} ---\n{c.chunk_text}")
            
        # Append resolved footnotes explicitly
        if final_ctx.resolved_refs:
            output.append("--- RESOLVED FOOTNOTES ---")
            for ref in final_ctx.resolved_refs:
                output.append(f"{ref['ref_code']} (From {ref['source']}):\n{ref['resolved_text']}")
            
        return "\n\n".join(output) if output else "No cross-references found."
