import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.tools.fetch_financial_statements_tool import fetch_financial_statements
from src.tools.search_narrative_disclosures_tool import search_narrative_disclosures
from src.rag.models.schemas import ChunkWithContext, ChunkMetadata, ScoredChunk

# Helper to create a fake chunk
def create_fake_chunk(text: str, section: str):
    meta = ChunkMetadata(
        company_id="TCS",
        report_type="annual",
        fiscal_year=2024,
        section_type=section,
        section_path=[],
        page_range=[1, 2],
        content_type="text",
        has_footnote_refs=False,
        document_id="fake_id",
        chunk_index=0
    )
    return ScoredChunk(
        chunk_id="fake_chunk_id",
        chunk_text=text,
        metadata=meta,
        score=0.99
    )

@pytest.mark.asyncio
@patch("src.tools.fetch_financial_statements_tool.SessionLocal")
@patch("src.tools.fetch_financial_statements_tool.HybridRetriever")
@patch("src.tools.fetch_financial_statements_tool.ContextAssembler")
async def test_fetch_financial_statements(mock_assembler_cls, mock_retriever_cls, mock_session):
    """Test the fetch_financial_statements wrapper."""
    # Setup ContextAssembler mock
    mock_assembler = MagicMock()
    mock_assembler_cls.return_value = mock_assembler
    
    # Setup the assembled context return
    fake_ctx = MagicMock()
    fake_ctx.chunks = [create_fake_chunk("Revenue: 100", "balance_sheet")]
    mock_assembler.assemble.return_value = fake_ctx
    
    # Setup HybridRetriever mock
    mock_retriever = MagicMock()
    # It uses an async method _execute_tree_navigation
    mock_retriever._execute_tree_navigation = AsyncMock()
    mock_retriever._execute_tree_navigation.return_value = fake_ctx.chunks
    mock_retriever_cls.return_value = mock_retriever

    # Execute
    result = await fetch_financial_statements.ainvoke({
        "company_id": "TCS",
        "fiscal_year": 2024,
        "statement_type": "balance_sheet"
    })
    
    # Verify the tool formatted the chunk text properly
    assert "--- Section: balance_sheet ---" in result
    assert "Revenue: 100" in result
    
    # Verify it called the correct underlying RAG method
    mock_retriever._execute_tree_navigation.assert_awaited_once()

@pytest.mark.asyncio
@patch("src.tools.search_narrative_disclosures_tool.SessionLocal")
@patch("src.tools.search_narrative_disclosures_tool.HybridRetriever")
@patch("src.tools.search_narrative_disclosures_tool.ContextAssembler")
async def test_search_narrative_disclosures(mock_assembler_cls, mock_retriever_cls, mock_session):
    """Test the search_narrative_disclosures wrapper."""
    mock_assembler = MagicMock()
    mock_assembler_cls.return_value = mock_assembler
    
    fake_ctx = MagicMock()
    fake_ctx.chunks = [create_fake_chunk("Growth strategy...", "mda")]
    mock_assembler.assemble.return_value = fake_ctx
    
    mock_retriever = MagicMock()
    # Hybrid search is async
    mock_retriever._execute_hybrid_search = AsyncMock()
    mock_retriever._execute_hybrid_search.return_value = fake_ctx.chunks
    
    # Reranker is also async
    mock_reranker = AsyncMock()
    mock_reranker.rerank.return_value = fake_ctx.chunks
    mock_retriever.reranker = mock_reranker
    
    mock_retriever_cls.return_value = mock_retriever

    result = await search_narrative_disclosures.ainvoke({
        "query": "What is the growth strategy?",
        "company_id": "TCS",
        "fiscal_year": 2024
    })
    
    assert "--- Document: 2024 mda ---" in result
    assert "Growth strategy..." in result
    
    mock_retriever._execute_hybrid_search.assert_awaited_once()
    mock_reranker.rerank.assert_awaited_once()
