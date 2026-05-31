"""
Pydantic schemas for the RAG pipeline.

Three categories:
    1. Ingestion schemas  — Normalized pages, content blocks, table data
    2. Metadata schemas   — Chunk metadata, document metadata
    3. Query/Response     — Request/response models, routing decisions
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ═════════════════════════════════════════════════════════════
# 1. INGESTION SCHEMAS
# ═════════════════════════════════════════════════════════════


class MergedCell(BaseModel):
    """Describes a merged cell region in a table."""
    row_start: int
    row_end: int
    col_start: int
    col_end: int
    value: str


class TableData(BaseModel):
    """
    Canonicalized table representation.
    This is the fixed schema that the JSON normalizer produces,
    regardless of how Sarvam Vision formats its output.
    """
    headers: list[list[str]] = Field(
        default_factory=list,
        description="Multi-level headers (each inner list is one header row)",
    )
    rows: list[list[str]] = Field(
        default_factory=list,
        description="Data rows (each inner list is one row of cell values)",
    )
    merged_cells: list[MergedCell] = Field(
        default_factory=list,
        description="Information about merged/spanning cells",
    )
    footnotes: list[str] = Field(
        default_factory=list,
        description="Footnote markers found within table cells",
    )
    num_columns: int = 0
    num_rows: int = 0


class ContentBlock(BaseModel):
    """A single content element extracted from a page."""
    block_type: Literal["text", "table", "heading", "image", "list"]
    content_text: str | None = None          # For text/heading/list blocks
    table_data: TableData | None = None      # For table blocks
    table_html: str | None = None            # Raw HTML for table blocks
    heading_level: int | None = None         # For heading blocks (1-6)
    confidence: float = 1.0
    bounding_box: dict | None = None         # Optional spatial info from Sarvam
    page_number: int = 0


class NormalizedPage(BaseModel):
    """
    Fixed schema for a single page's extracted content.
    This is the output of the JSON normalizer — the first
    defensive layer after Sarvam Vision.
    """
    page_number: int
    content_blocks: list[ContentBlock] = Field(default_factory=list)
    raw_markdown: str = ""                   # Full markdown from Sarvam
    raw_html: str = ""                       # Full HTML from Sarvam


class ClassifiedSection(BaseModel):
    """A section after classification by the LLM classifier."""
    section_type: str                        # From SECTION_TYPES taxonomy
    section_path: list[str] = Field(
        default_factory=list,
        description='Hierarchical path, e.g., ["Financial Statements", "Balance Sheet"]',
    )
    content_type: Literal["table", "text", "mixed"] = "text"
    content_blocks: list[ContentBlock] = Field(default_factory=list)
    content_markdown: str = ""
    content_json: dict | None = None
    contextual_summary: str = ""
    page_start: int = 0
    page_end: int = 0


# ═════════════════════════════════════════════════════════════
# 2. METADATA SCHEMAS
# ═════════════════════════════════════════════════════════════


class DocumentMetadata(BaseModel):
    """Metadata about the source document, attached to every chunk."""
    company_id: str
    report_type: Literal["annual", "quarterly"]
    fiscal_year: int
    fiscal_quarter: str | None = None
    document_id: str = ""                    # UUID as string
    file_name: str = ""


class ChunkMetadata(BaseModel):
    """
    The full metadata schema attached to every chunk.
    This is stored in the `metadata` JSONB column on rag_section_chunks,
    and is the primary object used for filtering during retrieval.
    """
    company_id: str
    report_type: Literal["annual", "quarterly"]
    fiscal_year: int
    fiscal_quarter: str | None = None
    section_type: str                        # From SECTION_TYPES taxonomy
    section_path: list[str] = Field(default_factory=list)
    page_range: list[int] = Field(
        default_factory=list,
        description="[start_page, end_page]",
    )
    content_type: Literal["table", "text", "image"] = "text"
    has_footnote_refs: bool = False
    resolved_refs: list[str] = Field(
        default_factory=list,
        description="UUIDs of resolved reference sections",
    )
    contextual_summary: str = ""
    document_id: str = ""
    section_id: str = ""
    chunk_index: int = 0


class ChunkWithContext(BaseModel):
    """A chunk ready for embedding, with its contextual prefix attached."""
    chunk_text: str                          # Raw text
    metadata_prefix: str                     # Prepended context for embedding
    full_text_for_embedding: str             # metadata_prefix + chunk_text
    metadata: ChunkMetadata
    chunk_index: int = 0


# ═════════════════════════════════════════════════════════════
# 3. REFERENCE SCHEMAS
# ═════════════════════════════════════════════════════════════


class RawRef(BaseModel):
    """A raw footnote reference found during scanning."""
    ref_code: str                            # "Note 5", "(1)", "Schedule V"
    source_cell: str = ""                    # The cell text where it was found
    page_number: int = 0
    source_table_id: str = ""                # UUID of the source table


class ResolvedRef(BaseModel):
    """A footnote reference resolved to its target section."""
    ref_code: str
    source_table_id: str                     # UUID
    target_section_id: str                   # UUID
    resolved_text: str = ""                  # Snippet of the resolved note


# ═════════════════════════════════════════════════════════════
# 4. QUERY / RESPONSE SCHEMAS
# ═════════════════════════════════════════════════════════════


class QueryTier(str, Enum):
    """
    Four tiers of query complexity, each using a different
    retrieval strategy.
    """
    T1_FACT_LOOKUP = "T1"                    # "What was RIL's revenue in 2024?"
    T2_MULTI_SECTION = "T2"                  # "Compare revenue growth with margin changes"
    T3_CROSS_REFERENCE = "T3"               # "What does Note 5 in the balance sheet say?"
    T4_TEMPORAL_SYNTHESIS = "T4"             # "How has debt changed over 3 years?"


class MetadataFilter(BaseModel):
    """Filters applied to narrow down retrieval scope."""
    company_id: str | None = None
    fiscal_year: int | None = None
    fiscal_years: list[int] | None = None    # For T4 multi-year queries
    fiscal_quarter: str | None = None
    section_types: list[str] | None = None
    document_ids: list[str] | None = None


class RoutingDecision(BaseModel):
    """Output of the query router — determines retrieval strategy."""
    tier: QueryTier
    metadata_filters: MetadataFilter = Field(default_factory=MetadataFilter)
    retrieval_strategy: Literal[
        "pageindex_tree",    # T1: tree navigation
        "hybrid",            # T2: parallel pageindex + vector
        "pageindex_refs",    # T3: tree + ref resolution
        "vector_multi_doc",  # T4: vector across documents
    ] = "hybrid"
    explanation: str = ""


class ScoredChunk(BaseModel):
    """A chunk with its retrieval score, used throughout the retrieval pipeline."""
    chunk_id: str                            # UUID
    chunk_text: str
    metadata: ChunkMetadata
    score: float = 0.0
    score_source: str = "unknown"            # "dense", "bm25", "rrf", "reranker"


class QueryRequest(BaseModel):
    """Incoming query from the user."""
    query: str
    company_id: str | None = None
    fiscal_year: int | None = None
    fiscal_quarter: str | None = None
    section_types: list[str] | None = None
    top_k: int = 10


class RetrievedContext(BaseModel):
    """
    The final assembled context, ready to be passed to the LLM.
    Contains reranked chunks + resolved refs + metadata.
    """
    query: str
    query_tier: QueryTier
    chunks: list[ScoredChunk] = Field(default_factory=list)
    resolved_refs: list[dict] = Field(default_factory=list)
    total_tokens_estimate: int = 0
    retrieval_strategy: str = ""
    metadata_filters_applied: dict = Field(default_factory=dict)


# ═════════════════════════════════════════════════════════════
# 5. INGESTION STATUS / REQUEST SCHEMAS
# ═════════════════════════════════════════════════════════════


class IngestionRequest(BaseModel):
    """Request to ingest a PDF report."""
    pdf_path: str
    company_id: str
    report_type: Literal["annual", "quarterly"]
    fiscal_year: int
    fiscal_quarter: str | None = None


class IngestionStatus(BaseModel):
    """Status report during/after ingestion."""
    document_id: str
    status: str                              # pending | processing | completed | failed
    pages_processed: int = 0
    total_pages: int = 0
    sections_found: int = 0
    tables_found: int = 0
    chunks_created: int = 0
    errors: list[str] = Field(default_factory=list)


# ═════════════════════════════════════════════════════════════
# 6. LLM RESPONSE SCHEMAS (for structured output)
# ═════════════════════════════════════════════════════════════


class SectionClassifierResponse(BaseModel):
    """Structured output from the section classifier LLM call."""
    section_type: str
    section_path: list[str]
    content_type: Literal["table", "text", "mixed"]
    confidence: float = 1.0


class QueryRouterResponse(BaseModel):
    """Structured output from the query router LLM call."""
    tier: str                                # "T1" | "T2" | "T3" | "T4"
    company_id: str | None = None
    fiscal_year: int | None = None
    fiscal_years: list[int] | None = None
    section_types: list[str] | None = None
    explanation: str = ""


class ContextualSummaryResponse(BaseModel):
    """Structured output from the contextual summary LLM call."""
    summary: str
