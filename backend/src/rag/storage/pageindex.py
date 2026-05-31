"""
PageIndex — tree-based navigation for structured document sections.

Enables retrieving complete hierarchical structures (like a full
Balance Sheet or a specific Schedule) without breaking them into
vector chunks, preserving their tabular integrity.
"""

import logging
import uuid
from typing import Sequence, Any

from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from src.rag.models.database import RAGPageIndexNode

logger = logging.getLogger("vittsarathi.rag.storage.pageindex")


class PageIndexStore:
    """
    Data access layer for the hierarchical PageIndex tree.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_document_tree(self, document_id: str | uuid.UUID) -> dict[str, Any]:
        """
        Fetch the complete PageIndex tree for a document and 
        format it as a nested dictionary.
        """
        if isinstance(document_id, str):
            document_id = uuid.UUID(document_id)
            
        # Get all nodes for the document ordered by depth (roots first)
        query = select(RAGPageIndexNode).where(
            RAGPageIndexNode.document_id == document_id
        ).order_by(RAGPageIndexNode.node_depth.asc())
        
        nodes = self.db.execute(query).scalars().all()
        
        if not nodes:
            return {}
            
        # Build the tree
        tree: dict[str, Any] = {}
        node_map: dict[uuid.UUID, dict[str, Any]] = {}
        
        for node in nodes:
            node_dict = {
                "id": str(node.id),
                "title": node.node_title,
                "section_id": str(node.section_id) if node.section_id else None,
                "path": node.node_path,
                "data": node.tree_json or {},
                "children": []
            }
            
            node_map[node.id] = node_dict
            
            if node.parent_id is None:
                tree[str(node.id)] = node_dict
            elif node.parent_id in node_map:
                node_map[node.parent_id]["children"].append(node_dict)
                
        return tree

    def find_nodes_by_type(
        self, 
        document_id: str | uuid.UUID, 
        section_types: list[str]
    ) -> Sequence[RAGPageIndexNode]:
        """
        Find specific nodes in the tree based on their section type.
        This queries the tree_json payload for the 'section_type' key.
        """
        if isinstance(document_id, str):
            document_id = uuid.UUID(document_id)
            
        query = select(RAGPageIndexNode).where(
            and_(
                RAGPageIndexNode.document_id == document_id,
                # Query inside the JSONB column
                RAGPageIndexNode.tree_json['section_type'].astext.in_(section_types)
            )
        )
        
        return self.db.execute(query).scalars().all()

    def get_node(self, node_id: str | uuid.UUID) -> RAGPageIndexNode | None:
        """Fetch a single node by ID."""
        if isinstance(node_id, str):
            node_id = uuid.UUID(node_id)
            
        return self.db.query(RAGPageIndexNode).filter(RAGPageIndexNode.id == node_id).first()
