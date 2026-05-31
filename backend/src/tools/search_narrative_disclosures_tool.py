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
async def search_narrative_disclosures(query: str, company_id: str, fiscal_year: int = None) -> str:
    """
    Performs a semantic hybrid search over narrative and conversational sections of annual reports.
    Automatically filters to sections like 'mda' (Management Discussion), 'directors_report', 
    'vision_mission', and 'management_profile'.
    Use this for conceptual questions like strategy, market outlook, and management commentary.
    """
    with SessionLocal() as db:
        vector_store = VectorStore(db)
        page_index = PageIndexStore(db)
        ref_store = RefStore(db)
        doc_store = DocumentStore(db)
        
        narrative_sections = ["mda", "directors_report", "vision_mission", "management_profile"]
        
        request = QueryRequest(query=query)
        filters = MetadataFilter(
            company_id=company_id, 
            fiscal_year=fiscal_year, 
            section_types=narrative_sections
        )
        decision = RoutingDecision(
            tier=QueryTier.T2_MULTI_SECTION, 
            metadata_filters=filters, 
            retrieval_strategy="hybrid", 
            explanation="Forced T2 lookup"
        )
        
        retriever = HybridRetriever(vector_store, page_index)
        chunks = await retriever._execute_hybrid_search(request, decision)
        
        if chunks:
            # Re-rank results
            chunks = await retriever.reranker.rerank(query, chunks)
            
        ctx = RetrievedContext(
            query=request.query, 
            query_tier=QueryTier.T2_MULTI_SECTION, 
            chunks=chunks, 
            retrieval_strategy="hybrid", 
            metadata_filters_applied=filters.model_dump(exclude_none=True)
        )
        
        assembler = ContextAssembler(ref_store, doc_store)
        final_ctx = assembler.assemble(ctx)
        
        output = []
        for c in final_ctx.chunks:
            output.append(f"--- Document: {c.metadata.fiscal_year} {c.metadata.section_type} ---\n{c.chunk_text}")
            
        return "\n\n".join(output) if output else "No relevant narrative text found."
