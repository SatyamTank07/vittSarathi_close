"""
Ingestion Pipeline — master orchestrator for the full ingestion flow.

Ties together all ingestion components in sequence:
    PDF → Split → Sarvam Vision → Normalize → Classify → Extract Refs
    → Generate Summaries → Chunk → Embed → Store

This is the single entry point for ingesting a financial report PDF
into the RAG system.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.rag.config import (
    NARRATIVE_SECTION_TYPES,
    STRUCTURED_SECTION_TYPES,
)
from src.rag.models.schemas import (
    ChunkWithContext,
    ClassifiedSection,
    DocumentMetadata,
    IngestionRequest,
    IngestionStatus,
    NormalizedPage,
    RawRef,
    ResolvedRef,
)
from src.rag.models.database import (
    RAGDocument,
    RAGSection,
    RAGDocumentTable,
    RAGSectionChunk,
    RAGRefLink,
    RAGPageIndexNode,
)
from src.rag.ingestion.pdf_splitter import PDFSplitter
from src.rag.ingestion.sarvam_client import SarvamClient
from src.rag.ingestion.json_normalizer import JsonNormalizer
from src.rag.ingestion.section_classifier import SectionClassifier
from src.rag.ingestion.ref_extractor import RefExtractor
from src.rag.ingestion.chunker import ContextualChunker
from src.rag.ingestion.embedding_service import EmbeddingService

logger = logging.getLogger("vittsarathi.rag.ingestion.pipeline")


class IngestionPipeline:
    """
    Full ingestion flow:
        PDF → Split → Sarvam Vision → Normalize → Classify
        → Extract Refs → Chunk → Embed → Store

    Usage:
        pipeline = IngestionPipeline(db_session)
        status = await pipeline.ingest(request)
    """

    def __init__(self, db: Session):
        self.db = db
        self.splitter = PDFSplitter()
        self.sarvam = SarvamClient()
        self.normalizer = JsonNormalizer()
        self.classifier = SectionClassifier()
        self.ref_extractor = RefExtractor()
        self.chunker = ContextualChunker()
        self.embedding_service = EmbeddingService()

    async def ingest(self, request: IngestionRequest) -> IngestionStatus:
        """
        Main entry point. Ingests a single PDF report end-to-end.

        Args:
            request: IngestionRequest with pdf_path, company_id, etc.

        Returns:
            IngestionStatus with progress metrics and any errors.
        """
        status = IngestionStatus(
            document_id="",
            status="processing",
        )
        errors: list[str] = []

        try:
            # ─── Step 1: Split PDF & Check Dedup ────────────
            logger.info(f"[Pipeline] Step 1: Splitting PDF — {request.pdf_path}")
            split_result = self.splitter.split(request.pdf_path)
            status.total_pages = split_result.total_pages

            # Check for duplicate
            existing = (
                self.db.query(RAGDocument)
                .filter(RAGDocument.file_hash == split_result.file_hash)
                .first()
            )
            if existing:
                logger.info(
                    f"[Pipeline] Document already exists (id={existing.id}). "
                    f"Skipping re-ingestion."
                )
                status.document_id = str(existing.id)
                status.status = "already_exists"
                self.splitter.cleanup(split_result)
                return status

            # Create document record
            doc = RAGDocument(
                company_id=request.company_id,
                report_type=request.report_type,
                fiscal_year=request.fiscal_year,
                fiscal_quarter=request.fiscal_quarter,
                file_hash=split_result.file_hash,
                file_name=split_result.source_filename,
                total_pages=split_result.total_pages,
                ingestion_status="processing",
            )
            self.db.add(doc)
            self.db.commit()
            self.db.refresh(doc)
            status.document_id = str(doc.id)

            logger.info(
                f"[Pipeline] Document created: id={doc.id}, "
                f"{split_result.total_pages} pages, "
                f"{split_result.num_batches} batches"
            )

            # ─── Step 2: Sarvam Vision Processing ──────────
            logger.info("[Pipeline] Step 2: Sarvam Vision — processing batches")
            all_pages_data: dict[int, dict] = {}

            for batch in split_result.batches:
                logger.info(
                    f"[Pipeline]   Batch {batch.batch_index}: "
                    f"pages {batch.page_start}-{batch.page_end}"
                )
                try:
                    batch_results = await self.sarvam.process_pdf_batch(batch.file_path)

                    # Remap page numbers to absolute (document-level) page numbers
                    for relative_page, content in batch_results.items():
                        absolute_page = batch.page_start + relative_page - 1
                        all_pages_data[absolute_page] = content
                        status.pages_processed += 1

                except Exception as e:
                    error_msg = (
                        f"Batch {batch.batch_index} failed "
                        f"(pages {batch.page_start}-{batch.page_end}): {e}"
                    )
                    logger.error(f"[Pipeline] {error_msg}")
                    errors.append(error_msg)

            logger.info(
                f"[Pipeline] Sarvam complete: "
                f"{status.pages_processed}/{status.total_pages} pages processed"
            )

            # ─── Step 3: Normalize JSON ────────────────────
            logger.info("[Pipeline] Step 3: Normalizing JSON output")
            normalized_pages = self.normalizer.normalize_document(all_pages_data)
            logger.info(f"[Pipeline] Normalized {len(normalized_pages)} pages")

            # ─── Step 4: Classify Sections ─────────────────
            logger.info("[Pipeline] Step 4: Classifying sections")
            classified_sections = await self.classifier.classify_document(
                normalized_pages
            )
            status.sections_found = len(classified_sections)
            logger.info(f"[Pipeline] Classified {len(classified_sections)} sections")

            # ─── Step 5: Store Sections & Tables ───────────
            logger.info("[Pipeline] Step 5: Storing sections and tables")
            doc_metadata = DocumentMetadata(
                company_id=request.company_id,
                report_type=request.report_type,
                fiscal_year=request.fiscal_year,
                fiscal_quarter=request.fiscal_quarter,
                document_id=str(doc.id),
                file_name=split_result.source_filename,
            )

            section_id_map: dict[int, str] = {}  # section_index → UUID
            table_count = 0

            for idx, section in enumerate(classified_sections):
                # Generate contextual summary
                summary = await self._generate_section_summary(
                    section, doc_metadata
                )
                section.contextual_summary = summary

                # Create section record
                db_section = RAGSection(
                    document_id=doc.id,
                    section_type=section.section_type,
                    section_path=section.section_path,
                    content_markdown=section.content_markdown,
                    content_json=section.content_json,
                    contextual_summary=summary,
                    page_start=section.page_start,
                    page_end=section.page_end,
                    content_type=section.content_type,
                )
                self.db.add(db_section)
                self.db.flush()  # Get the ID without committing
                section_id_map[idx] = str(db_section.id)

                # Store tables within this section
                for block in section.content_blocks:
                    if block.block_type == "table" and block.table_data:
                        db_table = RAGDocumentTable(
                            section_id=db_section.id,
                            table_markdown=block.content_text or "",
                            table_json=(
                                block.table_data.model_dump()
                                if block.table_data else None
                            ),
                            table_html=block.table_html or "",
                            footnote_refs=block.table_data.footnotes if block.table_data else [],
                            contextual_summary=summary,
                            table_index=table_count,
                        )
                        self.db.add(db_table)
                        table_count += 1
                        status.tables_found += 1

            self.db.commit()
            logger.info(
                f"[Pipeline] Stored {len(section_id_map)} sections, "
                f"{table_count} tables"
            )

            # ─── Step 6: Extract & Resolve References ──────
            logger.info("[Pipeline] Step 6: Extracting and resolving references")
            raw_refs = self.ref_extractor.extract_all_refs(classified_sections)
            resolved_refs = self.ref_extractor.resolve_refs(
                raw_refs, classified_sections, section_id_map
            )

            # Store resolved refs
            for ref in resolved_refs:
                db_ref = RAGRefLink(
                    document_id=doc.id,
                    ref_code=ref.ref_code,
                    source_table_id=(
                        uuid.UUID(ref.source_table_id)
                        if ref.source_table_id else None
                    ),
                    target_section_id=(
                        uuid.UUID(ref.target_section_id)
                        if ref.target_section_id else None
                    ),
                    resolved_text=ref.resolved_text,
                )
                self.db.add(db_ref)

            self.db.commit()
            logger.info(f"[Pipeline] Stored {len(resolved_refs)} ref links")

            # ─── Step 7: Chunk & Embed Narrative Sections ──
            logger.info("[Pipeline] Step 7: Chunking and embedding narrative sections")
            narrative_sections = [
                s for s in classified_sections
                if s.section_type in NARRATIVE_SECTION_TYPES
            ]

            all_chunks: list[ChunkWithContext] = []
            for section in narrative_sections:
                chunks = await self.chunker.chunk_section(section, doc_metadata)
                all_chunks.extend(chunks)

            if all_chunks:
                # Generate embeddings in batch
                texts_to_embed = [c.full_text_for_embedding for c in all_chunks]
                embeddings = await self.embedding_service.embed_batch(texts_to_embed)

                # Store chunks with embeddings
                for chunk, embedding in zip(all_chunks, embeddings):
                    # Find the section UUID for this chunk
                    section_uuid = None
                    for idx, section in enumerate(classified_sections):
                        if section.section_type == chunk.metadata.section_type:
                            if idx in section_id_map:
                                section_uuid = uuid.UUID(section_id_map[idx])
                                break

                    db_chunk = RAGSectionChunk(
                        section_id=section_uuid,
                        chunk_text=chunk.chunk_text,
                        metadata_prefix=chunk.metadata_prefix,
                        chunk_index=chunk.chunk_index,
                        chunk_metadata=chunk.metadata.model_dump(),
                    )
                    self.db.add(db_chunk)

                self.db.commit()

                # Update embeddings via raw SQL (pgvector column)
                await self._store_embeddings(all_chunks, embeddings)

                status.chunks_created = len(all_chunks)
                logger.info(f"[Pipeline] Stored {len(all_chunks)} chunks with embeddings")
            else:
                logger.info("[Pipeline] No narrative sections to chunk")

            # ─── Step 8: Build PageIndex Tree ──────────────
            logger.info("[Pipeline] Step 8: Building PageIndex tree")
            structured_sections = [
                (idx, s) for idx, s in enumerate(classified_sections)
                if s.section_type in STRUCTURED_SECTION_TYPES
            ]

            if structured_sections:
                # Create root node
                root_node = RAGPageIndexNode(
                    document_id=doc.id,
                    node_title=f"{request.company_id} {request.report_type.title()} {request.fiscal_year}",
                    parent_id=None,
                    node_path=[request.company_id],
                    node_depth=0,
                )
                self.db.add(root_node)
                self.db.flush()

                # Create child nodes for each structured section
                for idx, section in structured_sections:
                    section_uuid = (
                        uuid.UUID(section_id_map[idx])
                        if idx in section_id_map else None
                    )

                    node = RAGPageIndexNode(
                        document_id=doc.id,
                        section_id=section_uuid,
                        node_title=" > ".join(section.section_path) if section.section_path else section.section_type,
                        parent_id=root_node.id,
                        node_path=section.section_path,
                        node_depth=1,
                        tree_json={
                            "section_type": section.section_type,
                            "page_range": [section.page_start, section.page_end],
                            "contextual_summary": section.contextual_summary,
                            "content_type": section.content_type,
                            "has_tables": any(
                                b.block_type == "table"
                                for b in section.content_blocks
                            ),
                        },
                    )
                    self.db.add(node)

                self.db.commit()
                logger.info(
                    f"[Pipeline] Built PageIndex tree: "
                    f"1 root + {len(structured_sections)} section nodes"
                )

            # ─── Step 9: Update FTS Vectors ────────────────
            logger.info("[Pipeline] Step 9: Updating full-text search vectors")
            await self._update_fts_vectors()

            # ─── Step 10: Finalize ─────────────────────────
            doc.ingestion_status = "completed"
            self.db.commit()

            # Cleanup temp files
            self.splitter.cleanup(split_result)

            status.status = "completed"
            status.errors = errors

            logger.info(
                f"[Pipeline] ══════ Ingestion complete ══════\n"
                f"  Document: {doc.id}\n"
                f"  Pages: {status.pages_processed}/{status.total_pages}\n"
                f"  Sections: {status.sections_found}\n"
                f"  Tables: {status.tables_found}\n"
                f"  Chunks: {status.chunks_created}\n"
                f"  Refs: {len(resolved_refs)}\n"
                f"  Errors: {len(errors)}"
            )

            return status

        except Exception as e:
            logger.error(f"[Pipeline] Fatal error during ingestion: {e}", exc_info=True)
            errors.append(f"Fatal: {str(e)}")

            # Update document status to failed
            if status.document_id:
                try:
                    doc = (
                        self.db.query(RAGDocument)
                        .filter(RAGDocument.id == uuid.UUID(status.document_id))
                        .first()
                    )
                    if doc:
                        doc.ingestion_status = "failed"
                        doc.error_message = str(e)[:1000]
                        self.db.commit()
                except Exception:
                    pass

            status.status = "failed"
            status.errors = errors
            return status

    # ─── Internal Helpers ───────────────────────────────────

    async def _generate_section_summary(
        self,
        section: ClassifiedSection,
        doc_metadata: DocumentMetadata,
    ) -> str:
        """Generate a contextual summary for a section."""
        try:
            # Reuse the chunker's summary generation
            summary = await self.chunker._generate_summary(section, doc_metadata)
            return summary
        except Exception as e:
            logger.warning(f"Summary generation failed: {e}")
            content = section.content_markdown or ""
            return content[:200].strip() + ("..." if len(content) > 200 else "")

    async def _store_embeddings(
        self,
        chunks: list[ChunkWithContext],
        embeddings: list[list[float]],
    ) -> None:
        """
        Store embedding vectors in the pgvector column via raw SQL.
        SQLAlchemy ORM can't handle the vector type directly, so we
        use a raw UPDATE statement.
        """
        from sqlalchemy import text

        # Get all chunk IDs in insertion order
        db_chunks = (
            self.db.query(RAGSectionChunk)
            .order_by(RAGSectionChunk.created_at.desc())
            .limit(len(chunks))
            .all()
        )

        # Reverse to match insertion order
        db_chunks = list(reversed(db_chunks))

        for db_chunk, embedding in zip(db_chunks, embeddings):
            vector_str = "[" + ",".join(str(v) for v in embedding) + "]"
            self.db.execute(
                text(
                    "UPDATE rag_section_chunks SET embedding = :vec "
                    "WHERE id = :chunk_id"
                ),
                {"vec": vector_str, "chunk_id": str(db_chunk.id)},
            )

        self.db.commit()

    async def _update_fts_vectors(self) -> None:
        """
        Update the tsvector column for full-text search on all chunks
        that don't have one yet.
        """
        from sqlalchemy import text

        self.db.execute(
            text("""
                UPDATE rag_section_chunks
                SET fts_vector = to_tsvector('english',
                    COALESCE(metadata_prefix, '') || ' ' || COALESCE(chunk_text, '')
                )
                WHERE fts_vector IS NULL
            """)
        )
        self.db.commit()
