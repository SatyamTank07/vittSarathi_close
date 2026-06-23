import pytest
import uuid
from sqlalchemy import text
from src.core.database.connection import engine, SessionLocal
from src.rag.models.database import (
    RAGDocument, RAGSection, RAGSectionChunk, RAGPageIndexNode, RAGRefLink, RAGDocumentTable
)
from src.rag.storage.pageindex import PageIndexStore
from src.rag.storage.ref_store import RefStore
from src.rag.storage.vector_store import VectorStore
from src.rag.models.schemas import MetadataFilter

def test_pageindex_tree_builder():
    """Test PageIndexStore tree construction"""
    db = SessionLocal()
    try:
        doc_id = uuid.uuid4()
        doc = RAGDocument(id=doc_id, company_id="TEST", report_type="annual", fiscal_year=2024, file_hash=str(uuid.uuid4()))
        db.add(doc)
        db.commit()

        # Add Root
        root_id = uuid.uuid4()
        root = RAGPageIndexNode(id=root_id, document_id=doc_id, node_title="Root", node_depth=0)
        db.add(root)
        db.commit()

        # Add Child
        child_id = uuid.uuid4()
        child = RAGPageIndexNode(id=child_id, document_id=doc_id, parent_id=root_id, node_title="Child 1", node_depth=1)
        db.add(child)
        db.commit()

        # Add Grandchild
        gchild_id = uuid.uuid4()
        gchild = RAGPageIndexNode(id=gchild_id, document_id=doc_id, parent_id=child_id, node_title="Grandchild 1", node_depth=2)
        db.add(gchild)
        db.commit()

        store = PageIndexStore(db)
        tree = store.get_document_tree(doc_id)

        # Assert tree structure
        assert str(root_id) in tree
        assert tree[str(root_id)]["title"] == "Root"
        
        children = tree[str(root_id)]["children"]
        assert len(children) == 1
        assert children[0]["title"] == "Child 1"
        
        grandchildren = children[0]["children"]
        assert len(grandchildren) == 1
        assert grandchildren[0]["title"] == "Grandchild 1"

    finally:
        db.execute(text("DELETE FROM rag_documents WHERE id = :id"), {"id": doc_id})
        db.commit()
        db.close()

def test_ref_store_resolver():
    """Test RefStore reference resolution"""
    db = SessionLocal()
    try:
        doc_id = uuid.uuid4()
        table_id = uuid.uuid4()
        sec_id = uuid.uuid4()
        
        doc = RAGDocument(id=doc_id, company_id="TEST", report_type="annual", fiscal_year=2024, file_hash=str(uuid.uuid4()))
        sec = RAGSection(id=sec_id, document_id=doc_id, section_type="notes")
        table = RAGDocumentTable(id=table_id, section_id=sec_id)
        db.add_all([doc, sec, table])
        db.commit()

        # Create RefLink
        ref = RAGRefLink(
            id=uuid.uuid4(),
            document_id=doc_id,
            ref_code="Note 5",
            source_table_id=table_id,
            target_section_id=sec_id,
            resolved_text="This is Note 5 content."
        )
        db.add(ref)
        db.commit()

        store = RefStore(db)
        
        # Test get_refs_by_codes
        refs = store.get_refs_by_codes(doc_id, ["Note 5", "NonExistent"])
        assert len(refs) == 1
        assert refs[0].resolved_text == "This is Note 5 content."
        assert str(refs[0].target_section_id) == str(sec_id)

        # Test get_refs_for_table
        table_refs = store.get_refs_for_table(table_id)
        assert len(table_refs) == 1
        assert table_refs[0].ref_code == "Note 5"

    finally:
        db.execute(text("DELETE FROM rag_documents WHERE id = :id"), {"id": doc_id})
        db.commit()
        db.close()

@pytest.mark.asyncio
async def test_vector_store_sparse_search():
    """Test VectorStore sparse (keyword) search with metadata filtering"""
    db = SessionLocal()
    try:
        doc_id = uuid.uuid4()
        sec_id = uuid.uuid4()
        chunk_id = uuid.uuid4()
        
        doc = RAGDocument(id=doc_id, company_id="TCS", report_type="annual", fiscal_year=2024, file_hash=str(uuid.uuid4()))
        sec = RAGSection(id=sec_id, document_id=doc_id, section_type="financials")
        db.add_all([doc, sec])
        db.commit()

        # Insert a chunk using raw SQL to properly set fts_vector
        db.execute(text("""
            INSERT INTO rag_section_chunks (id, section_id, chunk_text, metadata, fts_vector)
            VALUES (
                :id, :sec_id, 'Revenue grew by 20% due to cloud deals.',
                '{"company_id": "TCS", "report_type": "annual", "fiscal_year": 2024, "section_type": "financials"}'::jsonb,
                to_tsvector('english', 'Revenue grew by 20% due to cloud deals.')
            )
        """), {"id": chunk_id, "sec_id": sec_id})
        db.commit()

        store = VectorStore(db)
        
        # Search for exact keyword that exists
        filters = MetadataFilter(company_id="TCS", fiscal_year=2024)
        results = await store.search_sparse("cloud revenue", filters, top_k=5)
        
        assert len(results) == 1
        assert results[0].chunk_id == str(chunk_id)
        assert results[0].score_source == "sparse"

        # Search with wrong metadata filter (year 2023)
        bad_filters = MetadataFilter(company_id="TCS", fiscal_year=2023)
        bad_results = await store.search_sparse("cloud revenue", bad_filters, top_k=5)
        assert len(bad_results) == 0

    finally:
        db.execute(text("DELETE FROM rag_documents WHERE id = :id"), {"id": doc_id})
        db.commit()
        db.close()
