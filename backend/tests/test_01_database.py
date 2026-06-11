import pytest
import uuid
from sqlalchemy import text
from src.core.database.connection import engine, SessionLocal
from src.core.database.models import AnalysisReport
from src.rag.models.database import RAGDocument, RAGSection, RAGSectionChunk

def test_db_infrastructure():
    """Scenario 1: Infrastructure & Extensions Validation"""
    with engine.connect() as conn:
        # Check pgvector
        res = conn.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector'")).fetchone()
        assert res is not None, "pgvector extension is not installed in PostgreSQL."
        
        # Check pg_trgm
        res = conn.execute(text("SELECT extname FROM pg_extension WHERE extname = 'pg_trgm'")).fetchone()
        assert res is not None, "pg_trgm extension is not installed in PostgreSQL."
        
        # Check if embedding column exists
        res = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'rag_section_chunks' 
            AND column_name = 'embedding'
        """)).fetchone()
        assert res is not None, "The 'embedding' column was not created on the 'rag_section_chunks' table."

def test_pgvector_math():
    """Scenario 2: Vector Math & Cosine Similarity"""
    with engine.connect() as conn:
        doc_id = str(uuid.uuid4())
        sec_id = str(uuid.uuid4())
        chunk1_id = str(uuid.uuid4())
        chunk2_id = str(uuid.uuid4())
        
        # Insert dummy document and section to satisfy foreign keys
        conn.execute(text("""
            INSERT INTO rag_documents (id, company_id, report_type, fiscal_year, file_hash) 
            VALUES (:id, 'TEST_VEC', 'annual', 2024, :hash)
        """), {"id": doc_id, "hash": str(uuid.uuid4())})
        
        conn.execute(text("""
            INSERT INTO rag_sections (id, document_id, section_type) 
            VALUES (:id, :doc_id, 'other')
        """), {"id": sec_id, "doc_id": doc_id})
        
        # Create a 1536-dimensional mock vector close to [1.0, 0, 0...]
        vector1 = "[" + ",".join(["1.0" if i == 0 else "0.0" for i in range(1536)]) + "]"
        # Create a mock vector close to [-1.0, 0, 0...]
        vector2 = "[" + ",".join(["-1.0" if i == 0 else "0.0" for i in range(1536)]) + "]"
        
        conn.execute(text("""
            INSERT INTO rag_section_chunks (id, section_id, chunk_text, embedding) 
            VALUES (:id, :sec_id, 'chunk1', CAST(:vec AS vector))
        """), {"id": chunk1_id, "sec_id": sec_id, "vec": vector1})
        
        conn.execute(text("""
            INSERT INTO rag_section_chunks (id, section_id, chunk_text, embedding) 
            VALUES (:id, :sec_id, 'chunk2', CAST(:vec AS vector))
        """), {"id": chunk2_id, "sec_id": sec_id, "vec": vector2})
        
        conn.commit()

        # Perform a cosine distance (<=>) search using a query vector close to vector1
        query_vector = "[" + ",".join(["0.9" if i == 0 else "0.0" for i in range(1536)]) + "]"
        
        res = conn.execute(text("""
            SELECT id, embedding <=> CAST(:qvec AS vector) AS distance 
            FROM rag_section_chunks 
            WHERE id IN (:id1, :id2)
            ORDER BY distance ASC LIMIT 1
        """), {"qvec": query_vector, "id1": chunk1_id, "id2": chunk2_id}).fetchone()
        
        # We expect chunk1 to be the nearest neighbor
        assert str(res[0]) == chunk1_id, "Vector math failed; incorrect nearest neighbor returned."
        
        # Clean up mock records (cascade delete on document will remove section and chunks)
        conn.execute(text("DELETE FROM rag_documents WHERE id = :id"), {"id": doc_id})
        conn.commit()

def test_tsvector_fts():
    """Scenario 3: Full-Text Search / BM25"""
    with engine.connect() as conn:
        # Test the tokenization and match logic of PostgreSQL tsvector directly
        res = conn.execute(text("""
            SELECT to_tsvector('english', 'The company reports significant revenue growth in Q4 due to AI hardware sales.') 
            @@ to_tsquery('english', 'revenue & AI')
        """)).scalar()
        
        assert res is True, "FTS query failed to match tokenized keywords."

def test_analysis_report_crud():
    """Scenario 4: Orchestrator CRUD Safety"""
    db = SessionLocal()
    try:
        report_id = str(uuid.uuid4())
        
        # 1. CREATE
        report = AnalysisReport(
            id=report_id,
            ticker="TEST.NS",
            company_name="Test Corp",
            investment_verdict="Bullish",
            report_markdown="Initial thesis."
        )
        db.add(report)
        db.commit()
        
        # 2. READ
        fetched = db.query(AnalysisReport).filter(AnalysisReport.id == report_id).first()
        assert fetched is not None, "Failed to read inserted record."
        assert fetched.ticker == "TEST.NS", "Data mismatch on read."
        
        # 3. UPDATE
        fetched.report_markdown = "Updated thesis."
        db.commit()
        
        updated = db.query(AnalysisReport).filter(AnalysisReport.id == report_id).first()
        assert updated.report_markdown == "Updated thesis.", "Update failed to persist."
        
        # 4. DELETE
        db.delete(updated)
        db.commit()
        
        deleted = db.query(AnalysisReport).filter(AnalysisReport.id == report_id).first()
        assert deleted is None, "Failed to delete record."
    finally:
        db.close()
