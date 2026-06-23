import pytest
import uuid
from sqlalchemy.exc import IntegrityError
from src.core.database.connection import engine, SessionLocal
from src.rag.models.database import (
    RAGDocument, RAGSection, RAGSectionChunk, RAGDocumentTable,
    RAGRefLink, RAGPageIndexNode, init_rag_db
)

def test_init_rag_db_idempotency():
    """Test 5: Idempotent Initialization"""
    # Calling it once
    init_rag_db(engine)
    # Calling it a second time shouldn't crash
    try:
        init_rag_db(engine)
    except Exception as e:
        pytest.fail(f"init_rag_db is not idempotent, failed on second run: {e}")

def test_rag_document_lifecycle_cascading():
    """Test 1: RAG Document Lifecycle & Cascading Deletes"""
    db = SessionLocal()
    try:
        doc_id = uuid.uuid4()
        sec_id = uuid.uuid4()
        chunk_id = uuid.uuid4()
        
        # 1. Insert Document
        doc = RAGDocument(
            id=doc_id,
            company_id="TEST_CASCADE",
            report_type="annual",
            fiscal_year=2024,
            file_hash=str(uuid.uuid4())
        )
        db.add(doc)
        
        # 2. Insert Section
        sec = RAGSection(
            id=sec_id,
            document_id=doc_id,
            section_type="financials"
        )
        db.add(sec)
        
        # 3. Insert Chunk
        chunk = RAGSectionChunk(
            id=chunk_id,
            section_id=sec_id,
            chunk_text="Test Chunk text"
        )
        db.add(chunk)
        db.commit()
        
        # 4. Verify they exist
        assert db.query(RAGSection).filter(RAGSection.id == sec_id).first() is not None
        assert db.query(RAGSectionChunk).filter(RAGSectionChunk.id == chunk_id).first() is not None
        
        # 5. Delete Document
        db.delete(doc)
        db.commit()
        
        # 6. Verify cascade delete removed section and chunk
        assert db.query(RAGSection).filter(RAGSection.id == sec_id).first() is None, "Section was not cascade deleted!"
        assert db.query(RAGSectionChunk).filter(RAGSectionChunk.id == chunk_id).first() is None, "Chunk was not cascade deleted!"
        
    finally:
        db.close()

def test_jsonb_metadata_integrity():
    """Test 2: JSONB Metadata Integrity"""
    db = SessionLocal()
    try:
        doc_id = uuid.uuid4()
        sec_id = uuid.uuid4()
        chunk_id = uuid.uuid4()
        
        # Setup parents
        doc = RAGDocument(id=doc_id, company_id="TEST_JSON", report_type="annual", fiscal_year=2024, file_hash=str(uuid.uuid4()))
        sec = RAGSection(id=sec_id, document_id=doc_id, section_type="notes")
        db.add_all([doc, sec])
        
        # Complex JSON metadata
        complex_metadata = {
            "page": 5,
            "type": "financials",
            "metrics": {
                "revenue": "1B",
                "tags": ["AI", "Cloud"]
            }
        }
        
        chunk = RAGSectionChunk(
            id=chunk_id,
            section_id=sec_id,
            chunk_text="Testing metadata",
            chunk_metadata=complex_metadata
        )
        db.add(chunk)
        db.commit()
        
        # Fetch back and assert
        fetched_chunk = db.query(RAGSectionChunk).filter(RAGSectionChunk.id == chunk_id).first()
        assert fetched_chunk.chunk_metadata["metrics"]["revenue"] == "1B"
        assert "Cloud" in fetched_chunk.chunk_metadata["metrics"]["tags"]
        
        # Clean up
        db.delete(doc)
        db.commit()
    finally:
        db.close()

def test_foreign_key_safety_blocks():
    """Test 3: Foreign Key Constraints & Safety Blocks"""
    db = SessionLocal()
    try:
        fake_doc_id = uuid.uuid4()
        
        # Attempt to insert section for non-existent document
        sec = RAGSection(
            id=uuid.uuid4(),
            document_id=fake_doc_id,
            section_type="invalid_test"
        )
        db.add(sec)
        
        with pytest.raises(IntegrityError):
            db.commit()
            
    finally:
        db.rollback()  # Rollback the failed transaction
        db.close()

def test_pageindex_tree_structure():
    """Test 4: PageIndex Tree Structure"""
    db = SessionLocal()
    try:
        doc_id = uuid.uuid4()
        root_id = uuid.uuid4()
        child1_id = uuid.uuid4()
        child2_id = uuid.uuid4()
        
        doc = RAGDocument(id=doc_id, company_id="TEST_TREE", report_type="annual", fiscal_year=2024, file_hash=str(uuid.uuid4()))
        db.add(doc)
        
        # Root node
        root_node = RAGPageIndexNode(
            id=root_id,
            document_id=doc_id,
            node_title="Financial Statements",
            parent_id=None,
            node_depth=0
        )
        db.add(root_node)
        
        # Child 1
        child1 = RAGPageIndexNode(
            id=child1_id,
            document_id=doc_id,
            node_title="Balance Sheet",
            parent_id=root_id,
            node_depth=1
        )
        # Child 2
        child2 = RAGPageIndexNode(
            id=child2_id,
            document_id=doc_id,
            node_title="P&L",
            parent_id=root_id,
            node_depth=1
        )
        db.add_all([child1, child2])
        db.commit()
        
        # Fetch children of root
        children = db.query(RAGPageIndexNode).filter(RAGPageIndexNode.parent_id == root_id).all()
        
        assert len(children) == 2
        titles = [c.node_title for c in children]
        assert "Balance Sheet" in titles
        assert "P&L" in titles
        
        # Clean up
        db.delete(doc)
        db.commit()
    finally:
        db.close()
