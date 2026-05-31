"""
Reference Extractor — deterministic footnote and cross-reference resolver.

Scans all table cells for footnote-style annotations and resolves them
against the classified section tree. This is pure regex pattern matching —
NO LLM calls. O(1) lookup at retrieval time once the ref_links table
is populated.

Patterns detected:
    (1), (2), (a), (b)         — Numeric/alpha footnotes
    *, **, ***                 — Asterisk footnotes
    Note 5, Note 12           — Note references
    Refer Schedule V           — Schedule references
    See Note 3                 — Explicit cross-references
    #1, #2                     — Hash-style references
"""

import logging
import re
from typing import Any

from src.rag.models.schemas import (
    ClassifiedSection,
    ContentBlock,
    RawRef,
    ResolvedRef,
    TableData,
)

logger = logging.getLogger("vittsarathi.rag.ingestion.ref_extractor")


# ─────────────────────────────────────────────────────────────
# Footnote Patterns
# ─────────────────────────────────────────────────────────────

# Each pattern returns the ref_code as the first capture group.
# The compiled regex is stored alongside a human-readable label.
FOOTNOTE_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "note_ref",
        re.compile(r"(?:Note|note|NOTE)\s+(\d+)", re.IGNORECASE),
    ),
    (
        "see_note",
        re.compile(r"(?:See|see|SEE)\s+(?:Note|note)\s+(\d+)", re.IGNORECASE),
    ),
    (
        "refer_schedule",
        re.compile(
            r"(?:Refer|refer|REFER)\s+(?:Schedule|schedule|SCHEDULE)\s+([IVXLCDM]+|[A-Z])",
            re.IGNORECASE,
        ),
    ),
    (
        "schedule_ref",
        re.compile(
            r"(?:Schedule|schedule|SCHEDULE)\s+([IVXLCDM]+|[A-Z])\b",
            re.IGNORECASE,
        ),
    ),
    (
        "numeric_parens",
        re.compile(r"\((\d{1,3})\)"),
    ),
    (
        "alpha_parens",
        re.compile(r"\(([a-z])\)"),
    ),
    (
        "asterisks",
        re.compile(r"(\*{1,3})(?!\*)"),
    ),
    (
        "hash_ref",
        re.compile(r"#(\d{1,3})\b"),
    ),
    (
        "as_per_note",
        re.compile(r"(?:as\s+per|As\s+per|AS\s+PER)\s+(?:Note|note)\s+(\d+)", re.IGNORECASE),
    ),
]


class RefExtractor:
    """
    Extracts and resolves footnote references from table cells.

    Two-phase process:
        1. extract_refs(): Scan cells for footnote markers → list[RawRef]
        2. resolve_refs(): Match markers against section tree → list[ResolvedRef]

    Usage:
        extractor = RefExtractor()
        raw_refs = extractor.extract_refs_from_section(classified_section)
        resolved = extractor.resolve_refs(raw_refs, all_sections)
    """

    def extract_refs_from_table(
        self,
        table: TableData,
        page_number: int,
        source_table_id: str = "",
    ) -> list[RawRef]:
        """
        Scan all cells in a table for footnote-style annotations.

        Args:
            table: Canonicalized TableData from the normalizer.
            page_number: Page number for attribution.
            source_table_id: UUID of the DocumentTable row (set later during storage).

        Returns:
            List of RawRef with ref_code and source context.
        """
        refs: list[RawRef] = []
        seen: set[str] = set()

        # Collect all cells (headers + data rows)
        all_cells: list[str] = []
        for row in table.headers:
            all_cells.extend(row)
        for row in table.rows:
            all_cells.extend(row)

        for cell_text in all_cells:
            if not cell_text or not cell_text.strip():
                continue

            for pattern_name, pattern in FOOTNOTE_PATTERNS:
                for match in pattern.finditer(cell_text):
                    raw_code = match.group(0).strip()
                    normalized_code = self._normalize_ref_code(raw_code, pattern_name)

                    if normalized_code in seen:
                        continue
                    seen.add(normalized_code)

                    refs.append(RawRef(
                        ref_code=normalized_code,
                        source_cell=cell_text.strip(),
                        page_number=page_number,
                        source_table_id=source_table_id,
                    ))

        if refs:
            logger.debug(
                f"Page {page_number}: Found {len(refs)} refs — "
                f"{[r.ref_code for r in refs[:5]]}"
            )

        return refs

    def extract_refs_from_section(
        self, section: ClassifiedSection
    ) -> list[RawRef]:
        """
        Extract all refs from all tables within a classified section.

        Args:
            section: A ClassifiedSection with content_blocks.

        Returns:
            Combined list of RawRef from all tables in the section.
        """
        all_refs: list[RawRef] = []

        for block in section.content_blocks:
            if block.block_type == "table" and block.table_data:
                refs = self.extract_refs_from_table(
                    table=block.table_data,
                    page_number=block.page_number,
                )
                all_refs.extend(refs)

        return all_refs

    def extract_all_refs(
        self, sections: list[ClassifiedSection]
    ) -> list[RawRef]:
        """Extract refs from all sections in a document."""
        all_refs: list[RawRef] = []
        for section in sections:
            refs = self.extract_refs_from_section(section)
            all_refs.extend(refs)

        logger.info(f"Total refs extracted from document: {len(all_refs)}")
        return all_refs

    def resolve_refs(
        self,
        raw_refs: list[RawRef],
        sections: list[ClassifiedSection],
        section_id_map: dict[int, str] | None = None,
    ) -> list[ResolvedRef]:
        """
        Match ref_codes against the section tree to find target sections.

        Resolution logic:
            - "Note 5" → find section with section_type='note_to_accounts'
                          that contains 'Note 5' in its heading or section_path
            - "Schedule V" → find section with section_type='schedule'
                             that contains 'Schedule V' in its heading or section_path
            - "(1)", "(a)", "*" → search note_to_accounts sections for the marker

        Args:
            raw_refs: List of RawRef from extract_refs().
            sections: All ClassifiedSection in the document.
            section_id_map: Optional mapping from section index → section UUID
                            (populated during storage phase).

        Returns:
            List of ResolvedRef with target_section_id populated.
        """
        resolved: list[ResolvedRef] = []

        # Build lookup indices
        note_sections = [
            (i, s) for i, s in enumerate(sections)
            if s.section_type in ("note_to_accounts", "schedule")
        ]

        for raw_ref in raw_refs:
            target_idx = self._find_target_section(
                raw_ref.ref_code, note_sections
            )

            if target_idx is not None:
                target_section = sections[target_idx]
                target_id = ""
                if section_id_map and target_idx in section_id_map:
                    target_id = section_id_map[target_idx]

                # Extract a snippet of the resolved content
                snippet = self._extract_snippet(target_section, max_chars=500)

                resolved.append(ResolvedRef(
                    ref_code=raw_ref.ref_code,
                    source_table_id=raw_ref.source_table_id,
                    target_section_id=target_id,
                    resolved_text=snippet,
                ))
            else:
                logger.debug(f"Could not resolve ref: {raw_ref.ref_code}")

        logger.info(
            f"Resolved {len(resolved)}/{len(raw_refs)} refs "
            f"({len(raw_refs) - len(resolved)} unresolved)"
        )
        return resolved

    # ─── Internal Methods ───────────────────────────────────

    def _normalize_ref_code(self, raw_code: str, pattern_name: str) -> str:
        """
        Normalize a raw ref code into a canonical form.

        Examples:
            "Note  5" → "Note 5"
            "note 5"  → "Note 5"
            "REFER SCHEDULE V" → "Schedule V"
            "See Note 3" → "Note 3"
        """
        code = raw_code.strip()

        # Note references → "Note N"
        if pattern_name in ("note_ref", "see_note", "as_per_note"):
            match = re.search(r"(\d+)", code)
            if match:
                return f"Note {match.group(1)}"

        # Schedule references → "Schedule X"
        if pattern_name in ("refer_schedule", "schedule_ref"):
            match = re.search(r"([IVXLCDM]+|[A-Z])\s*$", code, re.IGNORECASE)
            if match:
                return f"Schedule {match.group(1).upper()}"

        # For simple markers, return as-is
        return code

    def _find_target_section(
        self,
        ref_code: str,
        note_sections: list[tuple[int, ClassifiedSection]],
    ) -> int | None:
        """
        Find the section index that matches a ref_code.

        Search strategy (in order of specificity):
            1. Exact match in section_path (e.g., "Note 5" in path)
            2. Partial match in section headings
            3. Content scan (the ref_code appears in the section's markdown)
        """
        ref_lower = ref_code.lower().strip()

        # Strategy 1: Match in section_path
        for idx, section in note_sections:
            for path_part in section.section_path:
                if ref_lower in path_part.lower():
                    return idx

        # Strategy 2: Match in heading blocks
        for idx, section in note_sections:
            for block in section.content_blocks:
                if block.block_type == "heading" and block.content_text:
                    if ref_lower in block.content_text.lower():
                        return idx

        # Strategy 3: Content scan for note number
        note_match = re.match(r"note\s+(\d+)", ref_lower)
        if note_match:
            note_num = note_match.group(1)
            for idx, section in note_sections:
                if section.section_type == "note_to_accounts":
                    # Check if this section's markdown mentions the note number
                    markdown_lower = section.content_markdown.lower()
                    # Look for "note 5" or "note 5:" or "5." at the start
                    if (
                        f"note {note_num}" in markdown_lower
                        or f"note {note_num}:" in markdown_lower
                        or f"note {note_num} " in markdown_lower
                    ):
                        return idx

        # Strategy 4: Schedule matching
        schedule_match = re.match(r"schedule\s+([ivxlcdm]+|[a-z])", ref_lower)
        if schedule_match:
            schedule_id = schedule_match.group(1).upper()
            for idx, section in note_sections:
                if section.section_type == "schedule":
                    for path_part in section.section_path:
                        if schedule_id in path_part.upper():
                            return idx
                    if f"schedule {schedule_id.lower()}" in section.content_markdown.lower():
                        return idx

        return None

    @staticmethod
    def _extract_snippet(section: ClassifiedSection, max_chars: int = 500) -> str:
        """Extract a text snippet from a section for the resolved_text field."""
        text = section.content_markdown or ""
        if len(text) > max_chars:
            text = text[:max_chars] + "..."
        return text.strip()
