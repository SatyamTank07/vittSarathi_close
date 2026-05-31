"""
Reference Store — lookup mechanisms for resolved footnote references.

Allows retrieving the target section content of a footnote (e.g. "Note 5")
that was detected inside a table.
"""

import logging
import uuid
from typing import Sequence

from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from src.rag.models.database import RAGRefLink

logger = logging.getLogger("vittsarathi.rag.storage.ref_store")


class RefStore:
    """
    Data access layer for resolved footnote references.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_refs_for_table(self, table_id: str | uuid.UUID) -> Sequence[RAGRefLink]:
        """
        Fetch all resolved references originating from a specific table.
        Used to enrich the context when an LLM asks about a table.
        """
        if isinstance(table_id, str):
            table_id = uuid.UUID(table_id)
            
        query = select(RAGRefLink).where(
            RAGRefLink.source_table_id == table_id
        )
        
        return self.db.execute(query).scalars().all()

    def get_refs_by_codes(
        self, 
        document_id: str | uuid.UUID, 
        ref_codes: list[str]
    ) -> Sequence[RAGRefLink]:
        """
        Fetch references in a document matching specific reference codes
        (e.g., ["Note 5", "Schedule V"]).
        """
        if isinstance(document_id, str):
            document_id = uuid.UUID(document_id)
            
        query = select(RAGRefLink).where(
            and_(
                RAGRefLink.document_id == document_id,
                RAGRefLink.ref_code.in_(ref_codes)
            )
        )
        
        return self.db.execute(query).scalars().all()

    def get_ref(self, ref_id: str | uuid.UUID) -> RAGRefLink | None:
        """Fetch a single reference by ID."""
        if isinstance(ref_id, str):
            ref_id = uuid.UUID(ref_id)
            
        return self.db.query(RAGRefLink).filter(RAGRefLink.id == ref_id).first()
