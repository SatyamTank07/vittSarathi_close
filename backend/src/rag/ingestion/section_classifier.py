"""
Section Classifier — LLM-based classification of document sections.

Tags each extracted section with a section_type from the fixed taxonomy
and builds a hierarchical section_path. This tag is the key that enables
metadata pre-filtering at query time.

Uses gpt-4o-mini with structured output for cost efficiency.
"""

import json
import logging
import os
from pathlib import Path

from jinja2 import Template
from langchain_openai import ChatOpenAI

from src.rag.config import (
    CLASSIFIER_MODEL,
    CLASSIFIER_MAX_TOKENS,
    CLASSIFIER_TEMPERATURE,
    PROMPTS_DIR,
    SECTION_TYPES,
)
from src.rag.models.schemas import (
    ClassifiedSection,
    ContentBlock,
    NormalizedPage,
    SectionClassifierResponse,
)

logger = logging.getLogger("vittsarathi.rag.ingestion.section_classifier")

# Load prompt template
_PROMPT_PATH = PROMPTS_DIR / "section_classifier.jinja2"
with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
    _PROMPT_TEMPLATE = Template(f.read())


class SectionClassifier:
    """
    Classifies sequences of content blocks into sections with
    typed labels from the SECTION_TYPES taxonomy.

    Usage:
        classifier = SectionClassifier()
        sections = await classifier.classify_document(normalized_pages)
    """

    def __init__(self, model: str = CLASSIFIER_MODEL):
        api_key = os.environ.get("OPENAI_API_KEY", "")
        api_key = api_key.strip('"').strip("'")

        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set.")

        self.llm = ChatOpenAI(
            model=model,
            temperature=CLASSIFIER_TEMPERATURE,
            max_tokens=CLASSIFIER_MAX_TOKENS,
            api_key=api_key,
        )

    async def classify_document(
        self, pages: list[NormalizedPage]
    ) -> list[ClassifiedSection]:
        """
        Process all pages of a document:
        1. Group consecutive pages by detected section boundaries
        2. Classify each group
        3. Build section_path hierarchy

        Args:
            pages: List of NormalizedPage from the JSON normalizer.

        Returns:
            List of ClassifiedSection, each tagged with section_type
            and section_path.
        """
        if not pages:
            return []

        # Step 1: Group pages into section candidates
        groups = self._group_pages_into_sections(pages)
        logger.info(f"Grouped {len(pages)} pages into {len(groups)} section candidates")

        # Step 2: Classify each group
        sections: list[ClassifiedSection] = []
        for group in groups:
            section = await self._classify_group(group)
            sections.append(section)

        logger.info(
            f"Classification complete: {len(sections)} sections — "
            f"{', '.join(s.section_type for s in sections[:5])}"
            f"{'...' if len(sections) > 5 else ''}"
        )

        return sections

    async def classify_single(
        self,
        content_blocks: list[ContentBlock],
        page_start: int,
        page_end: int,
    ) -> ClassifiedSection:
        """
        Classify a single sequence of content blocks.

        Args:
            content_blocks: List of ContentBlock for this section.
            page_start: First page number (1-indexed).
            page_end: Last page number (1-indexed).

        Returns:
            ClassifiedSection with section_type, section_path, content_type.
        """
        # Build content preview for the LLM
        preview = self._build_content_preview(content_blocks, max_chars=3000)

        # Render prompt
        prompt_text = _PROMPT_TEMPLATE.render(
            page_start=page_start,
            page_end=page_end,
            section_types=", ".join(SECTION_TYPES),
            content_preview=preview,
        )

        # Call LLM
        try:
            response = await self.llm.ainvoke(prompt_text)
            result = self._parse_response(response.content)
        except Exception as e:
            logger.warning(
                f"Classification failed for pages {page_start}-{page_end}: {e}. "
                f"Falling back to 'other'."
            )
            result = SectionClassifierResponse(
                section_type="other",
                section_path=["Unclassified"],
                content_type="text",
                confidence=0.0,
            )

        # Assemble the full markdown from all blocks
        content_markdown = self._blocks_to_markdown(content_blocks)

        # Determine content_json (only for blocks with table data)
        content_json = None
        tables_in_blocks = [
            b.table_data.model_dump() for b in content_blocks
            if b.block_type == "table" and b.table_data
        ]
        if tables_in_blocks:
            content_json = {"tables": tables_in_blocks}

        return ClassifiedSection(
            section_type=result.section_type,
            section_path=result.section_path,
            content_type=result.content_type,
            content_blocks=content_blocks,
            content_markdown=content_markdown,
            content_json=content_json,
            page_start=page_start,
            page_end=page_end,
        )

    # ─── Internal Methods ───────────────────────────────────

    def _group_pages_into_sections(
        self, pages: list[NormalizedPage]
    ) -> list[_SectionGroup]:
        """
        Group consecutive pages into section candidates based on
        heading detection. A new section starts when we see a
        heading block (level 1 or 2).
        """
        groups: list[_SectionGroup] = []
        current_blocks: list[ContentBlock] = []
        current_start: int = pages[0].page_number if pages else 1
        current_end: int = current_start

        for page in pages:
            for block in page.content_blocks:
                # Detect section boundary: heading level 1 or 2
                is_boundary = (
                    block.block_type == "heading"
                    and block.heading_level is not None
                    and block.heading_level <= 2
                    and current_blocks  # Don't start a new group if we have nothing yet
                )

                if is_boundary:
                    # Flush current group
                    groups.append(_SectionGroup(
                        blocks=current_blocks,
                        page_start=current_start,
                        page_end=current_end,
                    ))
                    current_blocks = []
                    current_start = page.page_number

                current_blocks.append(block)
                current_end = page.page_number

        # Flush last group
        if current_blocks:
            groups.append(_SectionGroup(
                blocks=current_blocks,
                page_start=current_start,
                page_end=current_end,
            ))

        # Merge very small groups (< 3 blocks) with the previous group
        merged: list[_SectionGroup] = []
        for group in groups:
            if merged and len(group.blocks) < 3:
                merged[-1].blocks.extend(group.blocks)
                merged[-1].page_end = group.page_end
            else:
                merged.append(group)

        return merged if merged else groups

    async def _classify_group(self, group: _SectionGroup) -> ClassifiedSection:
        """Classify a single section group."""
        return await self.classify_single(
            content_blocks=group.blocks,
            page_start=group.page_start,
            page_end=group.page_end,
        )

    def _parse_response(self, raw_text: str) -> SectionClassifierResponse:
        """Parse the LLM response into a structured SectionClassifierResponse."""
        # Strip markdown code fences if present
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines (```json and ```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            import re
            match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                raise ValueError(f"Could not parse JSON from LLM response: {text[:200]}")

        # Validate section_type is in our taxonomy
        section_type = data.get("section_type", "other")
        if section_type not in SECTION_TYPES:
            logger.warning(f"Unknown section_type '{section_type}', falling back to 'other'")
            section_type = "other"

        # Validate content_type
        content_type = data.get("content_type", "text")
        if content_type not in ("table", "text", "mixed"):
            content_type = "text"

        return SectionClassifierResponse(
            section_type=section_type,
            section_path=data.get("section_path", ["Unclassified"]),
            content_type=content_type,
        )

    @staticmethod
    def _build_content_preview(
        blocks: list[ContentBlock], max_chars: int = 3000
    ) -> str:
        """Build a text preview from content blocks for the LLM prompt."""
        parts: list[str] = []
        total = 0

        for block in blocks:
            if total >= max_chars:
                break

            if block.block_type == "heading" and block.content_text:
                prefix = "#" * (block.heading_level or 1)
                text = f"{prefix} {block.content_text}"
            elif block.block_type == "table" and block.content_text:
                text = f"[TABLE]\n{block.content_text}"
            elif block.content_text:
                text = block.content_text
            else:
                continue

            remaining = max_chars - total
            if len(text) > remaining:
                text = text[:remaining] + "..."

            parts.append(text)
            total += len(text)

        return "\n\n".join(parts)

    @staticmethod
    def _blocks_to_markdown(blocks: list[ContentBlock]) -> str:
        """Convert content blocks to a combined Markdown string."""
        parts: list[str] = []

        for block in blocks:
            if block.block_type == "heading" and block.content_text:
                prefix = "#" * (block.heading_level or 1)
                parts.append(f"{prefix} {block.content_text}")
            elif block.block_type == "table" and block.content_text:
                parts.append(block.content_text)
            elif block.content_text:
                parts.append(block.content_text)

        return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────
# Internal data class
# ─────────────────────────────────────────────────────────────

class _SectionGroup:
    """Temporary grouping of content blocks during section detection."""

    __slots__ = ("blocks", "page_start", "page_end")

    def __init__(
        self,
        blocks: list[ContentBlock],
        page_start: int,
        page_end: int,
    ):
        self.blocks = blocks
        self.page_start = page_start
        self.page_end = page_end
