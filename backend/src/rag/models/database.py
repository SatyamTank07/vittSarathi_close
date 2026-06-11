"""
SQLAlchemy ORM models for the RAG pipeline.

Six tables matching the storage architecture:
    1. rag_documents       — One row per ingested PDF
    2. rag_sections        — Every logical section in a document
    3. rag_document_tables — Every table with 3 format representations
    4. rag_section_chunks  — Narrative text split + embedded (vector store)
    5. rag_ref_links       — Footnote code → target section mapping
    6. rag_pageindex_nodes — PageIndex tree for structured sections

Uses the existing Base from src.core.database.connection and extends
the PostgreSQL database with pgvector and full-text search.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, Text, DateTime, ForeignKey,
    Index, text, func,
)
from sqlalchemy.dialects.postgresql import (
    UUID, JSONB, ARRAY, TSVECTOR,
)
from sqlalchemy.orm import relationship

from src.core.database.connection import Base


# ─────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────

def _utcnow():
    return datetime.now(timezone.utc)


def _new_uuid():
    return uuid.uuid4()


# ─────────────────────────────────────────────────────────────
# Table 1: Documents — one row per ingested PDF
# ─────────────────────────────────────────────────────────────

class RAGDocument(Base):
    """Tracks every PDF report ingested into the system."""

    __tablename__ = "rag_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    company_id = Column(Text, nullable=False, index=True)
    report_type = Column(Text, nullable=False)             # "annual" | "quarterly"
    fiscal_year = Column(Integer, nullable=False)
    fiscal_quarter = Column(Text, nullable=True)           # "Q1" | "Q2" | "Q3" | "Q4" | None
    file_hash = Column(Text, unique=True, nullable=False)  # SHA-256 for dedup
    file_name = Column(Text, nullable=True)                # Original filename
    total_pages = Column(Integer, nullable=True)
    ingestion_status = Column(Text, default="pending")     # pending | processing | completed | failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    sections = relationship("RAGSection", back_populates="document", cascade="all, delete-orphan")
    ref_links = relationship("RAGRefLink", back_populates="document", cascade="all, delete-orphan")
    pageindex_nodes = relationship("RAGPageIndexNode", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self):
        return (
            f"<RAGDocument(id={self.id}, company={self.company_id}, "
            f"fy={self.fiscal_year}, status={self.ingestion_status})>"
        )


# ─────────────────────────────────────────────────────────────
# Table 2: Sections — every logical section in a document
# ─────────────────────────────────────────────────────────────

class RAGSection(Base):
    """
    A logical section extracted from a document.
    Tagged with section_type from the fixed taxonomy.
    """

    __tablename__ = "rag_sections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rag_documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    section_type = Column(Text, nullable=False, index=True)
    section_path = Column(ARRAY(Text))                       # ["Financial Statements", "Balance Sheet"]
    content_markdown = Column(Text)                          # Full markdown of section
    content_json = Column(JSONB)                             # Normalized JSON from Sarvam
    contextual_summary = Column(Text)                        # LLM-generated 1-sentence summary
    page_start = Column(Integer, nullable=True)
    page_end = Column(Integer, nullable=True)
    content_type = Column(Text, default="text")              # "table" | "text" | "mixed"
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    document = relationship("RAGDocument", back_populates="sections")
    tables = relationship("RAGDocumentTable", back_populates="section", cascade="all, delete-orphan")
    chunks = relationship("RAGSectionChunk", back_populates="section", cascade="all, delete-orphan")
    pageindex_nodes = relationship("RAGPageIndexNode", back_populates="section", cascade="all, delete-orphan")

    def __repr__(self):
        return (
            f"<RAGSection(id={self.id}, type={self.section_type}, "
            f"pages={self.page_start}-{self.page_end})>"
        )


# ─────────────────────────────────────────────────────────────
# Table 3: Document Tables — 3 format representations per table
# ─────────────────────────────────────────────────────────────

class RAGDocumentTable(Base):
    """
    Every table extracted from a document, stored in three formats
    for different consumption needs: Markdown (LLM), JSON (structured),
    HTML (layout-preserving).
    """

    __tablename__ = "rag_document_tables"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    section_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rag_sections.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    table_markdown = Column(Text)                            # Markdown table
    table_json = Column(JSONB)                               # Canonicalized {headers, rows, merged_cells}
    table_html = Column(Text)                                # HTML table from Sarvam
    footnote_refs = Column(ARRAY(Text))                      # ["(1)", "Note 5", "Schedule V"]
    contextual_summary = Column(Text)                        # LLM-generated summary of table content
    table_index = Column(Integer, nullable=True)             # Order within section
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    section = relationship("RAGSection", back_populates="tables")
    source_refs = relationship("RAGRefLink", back_populates="source_table", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<RAGDocumentTable(id={self.id}, section={self.section_id})>"


# ─────────────────────────────────────────────────────────────
# Table 4: Section Chunks — narrative text, split + embedded
# ─────────────────────────────────────────────────────────────

class RAGSectionChunk(Base):
    """
    A chunk of narrative text from a section, embedded for vector search
    and indexed for BM25 full-text search. Each chunk carries the full
    metadata schema and a contextual prefix.
    """

    __tablename__ = "rag_section_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    section_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rag_sections.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    chunk_text = Column(Text, nullable=False)                # Raw chunk text
    metadata_prefix = Column(Text)                           # Contextual prefix prepended before embedding
    chunk_index = Column(Integer, nullable=True)             # Order within section

    # Embedding — stored via pgvector extension
    # The actual Vector(1536) column is created by the init_rag_db()
    # function using raw SQL, since pgvector's SQLAlchemy integration
    # requires the extension to be installed first.
    # Column name: "embedding" vector(1536)

    # Full-text search — PostgreSQL tsvector for BM25-style search
    fts_vector = Column(TSVECTOR)

    # Full metadata as JSON (for filtering during retrieval)
    chunk_metadata = Column("metadata", JSONB)

    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    section = relationship("RAGSection", back_populates="chunks")

    def __repr__(self):
        return (
            f"<RAGSectionChunk(id={self.id}, section={self.section_id}, "
            f"idx={self.chunk_index})>"
        )


# ─────────────────────────────────────────────────────────────
# Table 5: Ref Links — footnote code → target section
# ─────────────────────────────────────────────────────────────

class RAGRefLink(Base):
    """
    Maps footnote references found in tables to their target sections.
    For example: "Note 5" in a balance sheet → the Note 5 section content.
    O(1) lookup at retrieval time.
    """

    __tablename__ = "rag_ref_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rag_documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    ref_code = Column(Text, nullable=False)                  # "Note 5", "(1)", "Schedule V"
    source_table_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rag_document_tables.id", ondelete="SET NULL"),
        nullable=True,
    )
    target_section_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rag_sections.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_text = Column(Text)                             # Snippet of resolved note content
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    document = relationship("RAGDocument", back_populates="ref_links")
    source_table = relationship("RAGDocumentTable", back_populates="source_refs")
    target_section = relationship("RAGSection")

    def __repr__(self):
        return f"<RAGRefLink(ref={self.ref_code}, target={self.target_section_id})>"


# ─────────────────────────────────────────────────────────────
# Table 6: PageIndex Nodes — tree for structured sections
# ─────────────────────────────────────────────────────────────

class RAGPageIndexNode(Base):
    """
    A node in the hierarchical document tree (PageIndex).
    Structured financial data (balance sheets, P&L, schedules)
    is navigated through this tree rather than searched via vectors.

    Tree structure:
        Root (document)
        ├── Financial Statements
        │   ├── Consolidated Balance Sheet
        │   ├── Standalone P&L
        │   └── Cash Flow Statement
        ├── Notes to Accounts
        │   ├── Note 1: Significant Accounting Policies
        │   ├── Note 5: Property, Plant & Equipment
        │   └── ...
        └── Schedules
            ├── Schedule V: ...
            └── ...
    """

    __tablename__ = "rag_pageindex_nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rag_documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    section_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rag_sections.id", ondelete="SET NULL"),
        nullable=True,
    )
    node_title = Column(Text, nullable=False)
    parent_id = Column(UUID(as_uuid=True), nullable=True)   # Self-referential (root has None)
    node_path = Column(ARRAY(Text))                          # Full path from root
    node_depth = Column(Integer, default=0)                  # Depth in tree (0 = root)
    tree_json = Column(JSONB)                                # Subtree snapshot with table data
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    document = relationship("RAGDocument", back_populates="pageindex_nodes")
    section = relationship("RAGSection", back_populates="pageindex_nodes")

    def __repr__(self):
        return f"<RAGPageIndexNode(title={self.node_title}, depth={self.node_depth})>"


# ─────────────────────────────────────────────────────────────
# Indexes (created alongside tables)
# ─────────────────────────────────────────────────────────────

# GIN index on fts_vector for fast full-text search
Index(
    "ix_rag_section_chunks_fts",
    RAGSectionChunk.fts_vector,
    postgresql_using="gin",
)

# GIN index on metadata JSONB for fast metadata filtering
Index(
    "ix_rag_section_chunks_metadata",
    RAGSectionChunk.chunk_metadata,
    postgresql_using="gin",
)

# Compound index on document lookups
Index(
    "ix_rag_documents_company_year",
    RAGDocument.company_id,
    RAGDocument.fiscal_year,
)

# Index on ref_links for fast footnote lookups
Index(
    "ix_rag_ref_links_code",
    RAGRefLink.document_id,
    RAGRefLink.ref_code,
)

# Index for PageIndex tree traversal
Index(
    "ix_rag_pageindex_parent",
    RAGPageIndexNode.document_id,
    RAGPageIndexNode.parent_id,
)


# ─────────────────────────────────────────────────────────────
# Database Initialization
# ─────────────────────────────────────────────────────────────

def init_rag_db(engine) -> None:
    """
    Initialize all RAG tables and required PostgreSQL extensions.

    Call this once at startup (or from a setup script).
    It is safe to call multiple times — CREATE IF NOT EXISTS is used.

    Steps:
        1. Install pgvector extension
        2. Install pg_trgm extension (for trigram similarity)
        3. Create all ORM tables
        4. Add the embedding vector column (pgvector type)
        5. Create IVFFlat index on the embedding column
    """
    with engine.connect() as conn:
        # Step 1 & 2: Extensions
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        conn.commit()

    # Step 3: Create all tables defined above
    Base.metadata.create_all(bind=engine)

    with engine.connect() as conn:
        # Step 4: Add the embedding column if it doesn't exist
        # We use raw SQL because pgvector's Vector type needs
        # the extension installed first.
        conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'rag_section_chunks'
                    AND column_name = 'embedding'
                ) THEN
                    ALTER TABLE rag_section_chunks
                    ADD COLUMN embedding vector(1536);
                END IF;
            END $$;
        """))
        conn.commit()

        # Step 5: Create IVFFlat index for approximate nearest neighbor search
        # Only create if table has data (IVFFlat needs training data)
        # For initial setup, create a basic HNSW index instead
        conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_indexes
                    WHERE indexname = 'ix_rag_chunks_embedding_hnsw'
                ) THEN
                    CREATE INDEX ix_rag_chunks_embedding_hnsw
                    ON rag_section_chunks
                    USING hnsw (embedding vector_cosine_ops)
                    WITH (m = 16, ef_construction = 64);
                END IF;
            END $$;
        """))
        conn.commit()
