"""
Document Store — CRUD operations for Documents, Sections, and Tables.

This layer handles fetching full documents, specific sections by type,
and tables for context assembly. It abstracts away the raw SQLAlchemy
queries from the retrieval layer.
"""

import uuid
from typing import Sequence

from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_

from src.rag.models.database import (
    RAGDocument,
    RAGSection,
    RAGDocumentTable,
)


class DocumentStore:
    """
    Data access layer for documents, sections, and tables.
    """

    def __init__(self, db: Session):
        self.db = db

    # ─── Document Methods ───────────────────────────────────

    def get_document(self, document_id: str | uuid.UUID) -> RAGDocument | None:
        """Fetch a single document by ID."""
        if isinstance(document_id, str):
            document_id = uuid.UUID(document_id)
            
        return self.db.query(RAGDocument).filter(RAGDocument.id == document_id).first()

    def find_documents(
        self,
        company_id: str | None = None,
        fiscal_year: int | None = None,
        fiscal_years: list[int] | None = None,
        fiscal_quarter: str | None = None,
        report_type: str | None = None,
        status: str | None = "completed",
    ) -> Sequence[RAGDocument]:
        """
        Find documents matching metadata filters.
        """
        query = select(RAGDocument)
        filters = []

        if status:
            filters.append(RAGDocument.ingestion_status == status)
        
        if company_id:
            # Normalize spaces to underscores for robust matching
            normalized_company = company_id.replace(" ", "_")
            filters.append(RAGDocument.company_id.ilike(normalized_company))
            
        if report_type:
            filters.append(RAGDocument.report_type == report_type)
            
        if fiscal_quarter:
            filters.append(RAGDocument.fiscal_quarter == fiscal_quarter)

        if fiscal_year is not None:
            filters.append(RAGDocument.fiscal_year == fiscal_year)
        elif fiscal_years:
            filters.append(RAGDocument.fiscal_year.in_(fiscal_years))

        if filters:
            query = query.where(and_(*filters))

        query = query.order_by(RAGDocument.fiscal_year.desc())
        
        return self.db.execute(query).scalars().all()

    # ─── Section Methods ────────────────────────────────────

    def get_section(self, section_id: str | uuid.UUID) -> RAGSection | None:
        """Fetch a single section by ID."""
        if isinstance(section_id, str):
            section_id = uuid.UUID(section_id)
            
        return self.db.query(RAGSection).filter(RAGSection.id == section_id).first()

    def get_sections_by_type(
        self,
        document_id: str | uuid.UUID,
        section_types: list[str],
    ) -> Sequence[RAGSection]:
        """
        Fetch all sections of specific types for a given document.
        Useful for targeted context assembly (e.g., getting all notes).
        """
        if isinstance(document_id, str):
            document_id = uuid.UUID(document_id)
            
        query = select(RAGSection).where(
            and_(
                RAGSection.document_id == document_id,
                RAGSection.section_type.in_(section_types)
            )
        ).order_by(RAGSection.page_start.asc())
        
        return self.db.execute(query).scalars().all()

    # ─── Table Methods ──────────────────────────────────────

    def get_table(self, table_id: str | uuid.UUID) -> RAGDocumentTable | None:
        """Fetch a single table by ID."""
        if isinstance(table_id, str):
            table_id = uuid.UUID(table_id)
            
        return self.db.query(RAGDocumentTable).filter(RAGDocumentTable.id == table_id).first()

    def get_tables_for_section(
        self, section_id: str | uuid.UUID
    ) -> Sequence[RAGDocumentTable]:
        """Fetch all tables within a specific section."""
        if isinstance(section_id, str):
            section_id = uuid.UUID(section_id)
            
        query = select(RAGDocumentTable).where(
            RAGDocumentTable.section_id == section_id
        ).order_by(RAGDocumentTable.table_index.asc())
        
        return self.db.execute(query).scalars().all()
