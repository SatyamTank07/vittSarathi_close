import pytest
import os
import fitz
import uuid
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import text

from src.core.database.connection import engine, SessionLocal
from src.rag.ingestion.chunker import ContextualChunker
from src.rag.ingestion.pdf_splitter import PDFSplitter, SplitResult, BatchInfo
from src.rag.ingestion.pipeline import IngestionPipeline
from src.rag.models.schemas import (
    ClassifiedSection, DocumentMetadata, IngestionRequest, ContentBlock
)
from src.rag.models.database import RAGDocument

@pytest.mark.asyncio
@patch.dict('os.environ', {'OPENAI_API_KEY': ''}) # Disable LLM
async def test_chunker_token_limits():
    """Test ContextualChunker splits long text correctly based on tokens"""
    chunker = ContextualChunker(chunk_size=100, overlap=20)
    
    # Create a long text (approx 200 words -> ~250 tokens)
    long_text = "This is a test sentence. " * 50
    
    section = ClassifiedSection(
        section_type="directors_report",
        content_markdown=long_text,
        page_start=1,
        page_end=2
    )
    
    doc_metadata = DocumentMetadata(
        company_id="TCS",
        report_type="annual",
        fiscal_year=2024
    )
    
    chunks = await chunker.chunk_section(section, doc_metadata)
    
    # Since it's ~250 tokens, chunk size 100, overlap 20 (step 80)
    # Expected chunks: ~3-4
    assert len(chunks) >= 3
    
    # Check that metadata prefix is prepended
    assert "TCS | Annual Report 2024 | Directors Report" in chunks[0].metadata_prefix
    
    # Check that chunk indices are sequential
    assert chunks[0].chunk_index == 0
    assert chunks[1].chunk_index == 1

def test_pdf_splitter_logic():
    """Test PDFSplitter correctly batches a large PDF"""
    # Create a dummy 5-page PDF using PyMuPDF
    doc = fitz.open()
    for i in range(5):
        page = doc.new_page()
        page.insert_text((50, 50), f"Dummy page {i+1}")
    
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
        doc.save(temp_pdf.name)
        temp_pdf_path = temp_pdf.name
    doc.close()
    
    try:
        # Split into batches of 2
        splitter = PDFSplitter(max_pages_per_batch=2)
        result = splitter.split(temp_pdf_path)
        
        assert result.total_pages == 5
        assert result.num_batches == 3
        
        # Batch 1: pages 1-2
        assert result.batches[0].num_pages == 2
        assert result.batches[0].page_start == 1
        assert result.batches[0].page_end == 2
        
        # Batch 3: page 5
        assert result.batches[2].num_pages == 1
        assert result.batches[2].page_start == 5
        assert result.batches[2].page_end == 5
        
        # Cleanup split temp directory
        splitter.cleanup(result)
    finally:
        if os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)

@pytest.mark.asyncio
async def test_pipeline_integration_mocked():
    """Test full IngestionPipeline by mocking external services"""
    db = SessionLocal()
    pipeline = IngestionPipeline(db)
    
    # Mock PDFSplitter
    pipeline.splitter = MagicMock()
    mock_split_result = SplitResult(
        source_path="/fake/path.pdf", source_filename="path.pdf", file_hash=str(uuid.uuid4()),
        total_pages=1, num_batches=1, temp_dir="/tmp/fake",
        batches=[BatchInfo(batch_index=0, file_path="/fake/batch.pdf", page_start=1, page_end=1, num_pages=1)]
    )
    pipeline.splitter.split.return_value = mock_split_result
    
    # Mock Sarvam
    pipeline.sarvam = AsyncMock()
    pipeline.sarvam.process_pdf_batch.return_value = {1: {"raw": "data"}}
    
    # Mock Normalizer
    pipeline.normalizer = MagicMock()
    pipeline.normalizer.normalize_document.return_value = []
    
    # Mock Classifier
    pipeline.classifier = AsyncMock()
    mock_section = ClassifiedSection(
        section_type="mda",
        section_path=["Management Discussion"],
        content_markdown="Mock MDA content",
        content_type="text",
        page_start=1,
        page_end=1
    )
    pipeline.classifier.classify_document.return_value = [mock_section]
    
    # Mock RefExtractor
    pipeline.ref_extractor = MagicMock()
    pipeline.ref_extractor.extract_all_refs.return_value = []
    pipeline.ref_extractor.resolve_refs.return_value = []
    
    # Mock Embedder
    pipeline.embedding_service = AsyncMock()
    pipeline.embedding_service.embed_batch.return_value = [[0.1] * 1536 for _ in range(1)]
    
    # Disable LLM in Chunker for fast summary
    pipeline.chunker.llm = None
    
    try:
        request = IngestionRequest(
            pdf_path="/fake/path.pdf",
            company_id="TEST_PIPELINE",
            report_type="annual",
            fiscal_year=2024
        )
        
        status = await pipeline.ingest(request)
        
        assert status.status == "completed"
        assert status.sections_found == 1
        assert status.chunks_created > 0
        assert status.document_id is not None
        
        # Verify db insertion
        doc = db.query(RAGDocument).filter(RAGDocument.id == uuid.UUID(status.document_id)).first()
        assert doc is not None
        assert doc.company_id == "TEST_PIPELINE"
        assert doc.ingestion_status == "completed"
        
    finally:
        # Cleanup
        if status and status.document_id:
            db.execute(text("DELETE FROM rag_documents WHERE id = :id"), {"id": status.document_id})
            db.commit()
        db.close()
