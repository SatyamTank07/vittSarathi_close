import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.rag.retrieval.query_router import QueryRouter
from src.rag.retrieval.hybrid_retriever import HybridRetriever
from src.rag.retrieval.context_assembler import ContextAssembler
from src.rag.models.schemas import (
    QueryRequest, RoutingDecision, QueryTier, MetadataFilter,
    ScoredChunk, ChunkMetadata, RetrievedContext
)
from src.rag.models.database import RAGDocumentTable, RAGRefLink

@pytest.mark.asyncio
@patch('src.rag.retrieval.query_router.ChatOpenAI.ainvoke')
@patch.dict('os.environ', {'OPENAI_API_KEY': 'fake_key'})
async def test_query_router_classification(mock_ainvoke):
    """Test QueryRouter parsing of LLM response"""
    # Mock the LLM returning a valid JSON string
    mock_ainvoke.return_value.content = '''```json
    {
        "tier": "T1",
        "company_id": "TCS",
        "fiscal_year": 2024,
        "section_types": ["financials"],
        "explanation": "Looking for exact revenue numbers."
    }
    ```'''
    
    router = QueryRouter()
    request = QueryRequest(query="What is TCS revenue in 2024?")
    decision = await router.route_query(request)
    
    assert decision.tier == QueryTier.T1_FACT_LOOKUP
    assert decision.metadata_filters.company_id == "TCS"
    assert decision.metadata_filters.fiscal_year == 2024
    assert decision.retrieval_strategy == "pageindex_tree"

@pytest.mark.asyncio
async def test_hybrid_retriever_orchestration():
    """Test HybridRetriever calls the correct sub-services based on router decision"""
    mock_vector_store = AsyncMock()
    mock_pageindex_store = AsyncMock()
    
    retriever = HybridRetriever(mock_vector_store, mock_pageindex_store)
    
    # Mock router to return T2 decision
    retriever.router = AsyncMock()
    retriever.router.route_query.return_value = RoutingDecision(
        tier=QueryTier.T2_MULTI_SECTION,
        metadata_filters=MetadataFilter(company_id="TCS", fiscal_year=2024),
        retrieval_strategy="hybrid"
    )
    
    # Mock embedding
    retriever.embedding_service = AsyncMock()
    retriever.embedding_service.embed_query.return_value = [0.1, 0.2, 0.3]
    
    # Mock vector search
    mock_chunk = ScoredChunk(
        chunk_id="chunk1",
        chunk_text="Test chunk",
        metadata=ChunkMetadata(company_id="TCS", report_type="annual", fiscal_year=2024, section_type="financials"),
        score=0.9
    )
    mock_vector_store.hybrid_search.return_value = [mock_chunk]
    
    # Mock reranker
    retriever.reranker = AsyncMock()
    retriever.reranker.rerank.return_value = [mock_chunk]
    
    # Execute
    request = QueryRequest(query="How did margin change?", company_id="TCS", fiscal_year=2024)
    result = await retriever.retrieve(request)
    
    # Verify vector search was called (because it's T2)
    mock_vector_store.hybrid_search.assert_called_once()
    assert len(result.chunks) == 1
    assert result.chunks[0].chunk_id == "chunk1"
    assert result.query_tier == QueryTier.T2_MULTI_SECTION

def test_context_assembler_ref_resolution():
    """Test ContextAssembler resolves references and calculates tokens"""
    mock_ref_store = MagicMock()
    mock_doc_store = MagicMock()
    
    # Create fake chunks, one is a table
    chunk1 = ScoredChunk(
        chunk_id="c1",
        chunk_text="Some table data",
        metadata=ChunkMetadata(
            company_id="TCS", report_type="annual", fiscal_year=2024, 
            section_type="financials", content_type="table", section_id="sec1"
        )
    )
    
    context = RetrievedContext(
        query="Test query",
        query_tier=QueryTier.T3_CROSS_REFERENCE,
        chunks=[chunk1]
    )
    
    # Mock DB returns
    fake_table = RAGDocumentTable(id="table1", section_id="sec1")
    mock_doc_store.get_tables_for_section.return_value = [fake_table]
    
    fake_ref = RAGRefLink(id="ref1", document_id="doc1", ref_code="Note 5", source_table_id="table1", target_section_id="sec2", resolved_text="This is Note 5")
    mock_ref_store.get_refs_for_table.return_value = [fake_ref]
    
    assembler = ContextAssembler(mock_ref_store, mock_doc_store)
    
    # Execute
    enriched = assembler.assemble(context, max_tokens=1000)
    
    # Verify ref was resolved
    mock_doc_store.get_tables_for_section.assert_called_with("sec1")
    mock_ref_store.get_refs_for_table.assert_called_with("table1")
    
    assert len(enriched.resolved_refs) == 1
    assert enriched.resolved_refs[0]["ref_code"] == "Note 5"
    assert enriched.resolved_refs[0]["resolved_text"] == "This is Note 5"
    
    # Verify token count was estimated (will be > 0)
    assert enriched.total_tokens_estimate > 0
