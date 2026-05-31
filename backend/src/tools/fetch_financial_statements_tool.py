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
async def fetch_financial_statements(company_id: str, fiscal_year: int, statement_type: str) -> str:
    """
    Fetches exact, intact tabular financial statements for a given company and fiscal year.
    Valid statement_type values include: 'balance_sheet', 'profit_loss', 'cash_flow', 'schedule'.
    Use this tool when you need exact line items, revenues, margins, or tabular data.
    """
    with SessionLocal() as db:
        vector_store = VectorStore(db)
        page_index = PageIndexStore(db)
        ref_store = RefStore(db)
        doc_store = DocumentStore(db)
        
        request = QueryRequest(query=f"Get {statement_type} for {company_id} {fiscal_year}")
        filters = MetadataFilter(
            company_id=company_id, 
            fiscal_year=fiscal_year, 
            section_types=[statement_type]
        )
        decision = RoutingDecision(
            tier=QueryTier.T1_FACT_LOOKUP, 
            metadata_filters=filters, 
            retrieval_strategy="pageindex_tree", 
            explanation="Forced T1 lookup"
        )
        
        retriever = HybridRetriever(vector_store, page_index)
        # Execute forced T1 lookup
        chunks = await retriever._execute_tree_navigation(request, decision)
        
        ctx = RetrievedContext(
            query=request.query, 
            query_tier=QueryTier.T1_FACT_LOOKUP, 
            chunks=chunks, 
            retrieval_strategy="tree", 
            metadata_filters_applied=filters.model_dump(exclude_none=True)
        )
        
        assembler = ContextAssembler(ref_store, doc_store)
        final_ctx = assembler.assemble(ctx)
        
        output = []
        for c in final_ctx.chunks:
            output.append(f"--- Section: {c.metadata.section_type} ---\n{c.chunk_text}")
            
        return "\n\n".join(output) if output else "No tabular financial statements found."
