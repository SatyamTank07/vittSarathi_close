"""
Contextual Chunker — splits narrative sections into chunks with metadata prefixes.

Each chunk gets a contextual prefix prepended before embedding:
    "[RIL | Annual Report 2024 | Directors Report]
     Summary: Management discusses competitive landscape and market share growth...

     <actual chunk text>"

Only narrative sections are chunked (mda, directors_report, risk_factors, etc.).
Structured sections (balance sheets, schedules) go to PageIndex instead.
"""

import logging
import os

import tiktoken
from jinja2 import Template

from langchain_openai import ChatOpenAI

from src.rag.config import (
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    CLASSIFIER_MODEL,
    PROMPTS_DIR,
)
from src.rag.models.schemas import (
    ChunkMetadata,
    ChunkWithContext,
    ClassifiedSection,
    DocumentMetadata,
)

logger = logging.getLogger("vittsarathi.rag.ingestion.chunker")

# Load the contextual summary prompt
_SUMMARY_PROMPT_PATH = PROMPTS_DIR / "contextual_summary.jinja2"
with open(_SUMMARY_PROMPT_PATH, "r", encoding="utf-8") as f:
    _SUMMARY_TEMPLATE = Template(f.read())


class ContextualChunker:
    """
    Splits narrative sections into overlapping token-based chunks,
    prepends contextual metadata, and generates LLM summaries.

    Usage:
        chunker = ContextualChunker()
        chunks = await chunker.chunk_section(section, doc_metadata)
    """

    def __init__(
        self,
        chunk_size: int = CHUNK_SIZE,
        overlap: int = CHUNK_OVERLAP,
        model: str = CLASSIFIER_MODEL,
    ):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.tokenizer = tiktoken.encoding_for_model("gpt-4o-mini")

        api_key = os.environ.get("OPENAI_API_KEY", "")
        api_key = api_key.strip('"').strip("'")
        self.llm = ChatOpenAI(
            model=model,
            temperature=0.1,
            max_tokens=200,
            api_key=api_key,
        ) if api_key else None

    async def chunk_section(
        self,
        section: ClassifiedSection,
        doc_metadata: DocumentMetadata,
    ) -> list[ChunkWithContext]:
        """
        Split a narrative section into contextual chunks.

        Steps:
            1. Get or generate contextual summary for the section
            2. Split text by token count with overlap
            3. Build metadata prefix for each chunk
            4. Return chunks ready for embedding

        Args:
            section: Classified section with content_markdown.
            doc_metadata: Document-level metadata (company, year, etc.).

        Returns:
            List of ChunkWithContext, each with full_text_for_embedding.
        """
        text = section.content_markdown or ""
        if not text.strip():
            return []

        # Step 1: Generate contextual summary if not already present
        summary = section.contextual_summary
        if not summary:
            summary = await self._generate_summary(section, doc_metadata)

        # Step 2: Split into token-based chunks with overlap
        raw_chunks = self._split_by_tokens(text)

        # Step 3: Build contextualized chunks
        chunks: list[ChunkWithContext] = []
        for i, chunk_text in enumerate(raw_chunks):
            # Build the metadata prefix
            prefix = self._build_prefix(
                doc_metadata=doc_metadata,
                section=section,
                summary=summary,
            )

            # Full text for embedding = prefix + chunk
            full_text = f"{prefix}\n\n{chunk_text}"

            # Build metadata object
            metadata = ChunkMetadata(
                company_id=doc_metadata.company_id,
                report_type=doc_metadata.report_type,
                fiscal_year=doc_metadata.fiscal_year,
                fiscal_quarter=doc_metadata.fiscal_quarter,
                section_type=section.section_type,
                section_path=section.section_path,
                page_range=[section.page_start, section.page_end],
                content_type="text",
                has_footnote_refs=False,
                contextual_summary=summary,
                document_id=doc_metadata.document_id,
                chunk_index=i,
            )

            chunks.append(ChunkWithContext(
                chunk_text=chunk_text,
                metadata_prefix=prefix,
                full_text_for_embedding=full_text,
                metadata=metadata,
                chunk_index=i,
            ))

        logger.info(
            f"Chunked section '{section.section_type}' "
            f"(pages {section.page_start}-{section.page_end}) → "
            f"{len(chunks)} chunks"
        )

        return chunks

    async def chunk_all_sections(
        self,
        sections: list[ClassifiedSection],
        doc_metadata: DocumentMetadata,
    ) -> list[ChunkWithContext]:
        """Chunk all narrative sections in a document."""
        all_chunks: list[ChunkWithContext] = []

        for section in sections:
            chunks = await self.chunk_section(section, doc_metadata)
            all_chunks.extend(chunks)

        logger.info(f"Total chunks created: {len(all_chunks)}")
        return all_chunks

    # ─── Token-based Splitting ──────────────────────────────

    def _split_by_tokens(self, text: str) -> list[str]:
        """
        Split text into chunks of `chunk_size` tokens with `overlap` token overlap.

        Uses tiktoken for accurate token counting aligned with the embedding model.
        Splits on sentence boundaries when possible to avoid mid-sentence cuts.
        """
        if not text.strip():
            return []

        tokens = self.tokenizer.encode(text)
        total_tokens = len(tokens)

        if total_tokens <= self.chunk_size:
            return [text]

        chunks: list[str] = []
        start = 0

        while start < total_tokens:
            end = min(start + self.chunk_size, total_tokens)

            # Decode this chunk's tokens back to text
            chunk_tokens = tokens[start:end]
            chunk_text = self.tokenizer.decode(chunk_tokens)

            # Try to end on a sentence boundary if we're not at the end
            if end < total_tokens:
                chunk_text = self._trim_to_sentence_boundary(chunk_text)

            chunk_text = chunk_text.strip()
            if chunk_text:
                chunks.append(chunk_text)

            # Move forward by (chunk_size - overlap)
            step = self.chunk_size - self.overlap
            start += max(step, 1)  # Ensure we always advance

        return chunks

    @staticmethod
    def _trim_to_sentence_boundary(text: str) -> str:
        """
        Trim text to the last sentence boundary (period, question mark, etc.).
        Falls back to the original text if no boundary is found.
        """
        # Look for the last sentence-ending punctuation followed by whitespace
        # Search from the end backwards
        for i in range(len(text) - 1, max(len(text) // 2, 0), -1):
            if text[i] in ".!?\n" and (i == len(text) - 1 or text[i + 1] in " \n\t"):
                return text[: i + 1]

        return text

    # ─── Summary Generation ─────────────────────────────────

    async def _generate_summary(
        self,
        section: ClassifiedSection,
        doc_metadata: DocumentMetadata,
    ) -> str:
        """
        Generate a one-sentence contextual summary for a section using LLM.

        This is a cheap call (gpt-4o-mini, ~200 tokens output) that pays
        back enormously at retrieval time.
        """
        if not self.llm:
            # Fallback: use first 200 chars of content as summary
            content = section.content_markdown or ""
            return content[:200].strip() + ("..." if len(content) > 200 else "")

        content_preview = (section.content_markdown or "")[:2500]
        section_path_str = " > ".join(section.section_path) if section.section_path else section.section_type

        prompt_text = _SUMMARY_TEMPLATE.render(
            company_id=doc_metadata.company_id,
            report_type=doc_metadata.report_type,
            fiscal_year=doc_metadata.fiscal_year,
            section_type=section.section_type,
            section_path=section_path_str,
            content_preview=content_preview,
        )

        try:
            response = await self.llm.ainvoke(prompt_text)
            summary = response.content.strip()
            # Remove any leading "Summary:" prefix the LLM might add
            if summary.lower().startswith("summary:"):
                summary = summary[8:].strip()
            return summary
        except Exception as e:
            logger.warning(f"Summary generation failed: {e}")
            content = section.content_markdown or ""
            return content[:200].strip() + ("..." if len(content) > 200 else "")

    # ─── Prefix Building ────────────────────────────────────

    @staticmethod
    def _build_prefix(
        doc_metadata: DocumentMetadata,
        section: ClassifiedSection,
        summary: str,
    ) -> str:
        """
        Build the metadata prefix that gets prepended to each chunk
        before embedding. This is the "contextual chunk" technique.

        Format:
            [COMPANY | REPORT_TYPE YEAR | SECTION_TYPE]
            Summary: <one-sentence summary>
        """
        report_label = f"{doc_metadata.report_type.title()} Report {doc_metadata.fiscal_year}"
        if doc_metadata.fiscal_quarter:
            report_label = f"{doc_metadata.fiscal_quarter} {doc_metadata.fiscal_year}"

        section_label = section.section_type.replace("_", " ").title()

        header = f"[{doc_metadata.company_id} | {report_label} | {section_label}]"

        if summary:
            return f"{header}\nSummary: {summary}"
        return header
