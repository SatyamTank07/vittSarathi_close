"""
JSON Normalizer — the most critical defensive step in the ingestion pipeline.

Takes raw, unpredictably-structured JSON from Sarvam Vision and canonicalizes
it into fixed Pydantic schemas (NormalizedPage, ContentBlock, TableData).

Why this matters:
    The JSON structure returned by Sarvam Vision varies between requests —
    fields sometimes missing, placed at different nesting levels, or named
    inconsistently. Every downstream component (section classifier, ref
    extractor, PageIndex builder) assumes well-formed input. If we don't
    normalize here, the entire pipeline breaks silently.

Strategy:
    For each field, we try 5+ fallback extraction paths. If all fail,
    we log a warning and use a safe default rather than crashing.
    Only truly unrecoverable corruption raises NormalizationError.
"""

import logging
import re
from typing import Any

from src.rag.models.schemas import (
    ContentBlock,
    MergedCell,
    NormalizedPage,
    TableData,
)

logger = logging.getLogger("vittsarathi.rag.ingestion.json_normalizer")


# ─────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────


class NormalizationError(Exception):
    """Raised when JSON normalization fails irrecoverably."""

    def __init__(self, message: str, raw_json: dict | None = None):
        self.raw_json = raw_json
        super().__init__(message)


# ─────────────────────────────────────────────────────────────
# Normalizer
# ─────────────────────────────────────────────────────────────


class JsonNormalizer:
    """
    Validates and canonicalizes Sarvam Vision JSON output
    into a fixed NormalizedPage schema.

    Usage:
        normalizer = JsonNormalizer()
        page = normalizer.normalize(raw_json, page_number=1)
    """

    def normalize(
        self,
        raw_json: dict,
        page_number: int,
        raw_html: str = "",
        raw_markdown: str = "",
    ) -> NormalizedPage:
        """
        Main entry point. Takes raw Sarvam JSON for a single page
        and produces a well-formed NormalizedPage.

        Args:
            raw_json: The raw JSON dict from Sarvam Vision for this page.
            page_number: 1-indexed page number.
            raw_html: Raw HTML output from Sarvam (if available).
            raw_markdown: Raw Markdown output from Sarvam (if available).

        Returns:
            NormalizedPage with fixed-schema content blocks.
        """
        if not raw_json and not raw_html and not raw_markdown:
            logger.warning(f"Page {page_number}: Empty input — returning empty page")
            return NormalizedPage(page_number=page_number)

        content_blocks: list[ContentBlock] = []

        # Extract content blocks from JSON
        if raw_json:
            blocks_from_json = self._extract_content_blocks(raw_json, page_number)
            content_blocks.extend(blocks_from_json)

        # If JSON yielded no blocks, try to extract from HTML/Markdown
        if not content_blocks and raw_html:
            blocks_from_html = self._extract_from_html(raw_html, page_number)
            content_blocks.extend(blocks_from_html)

        if not content_blocks and raw_markdown:
            blocks_from_md = self._extract_from_markdown(raw_markdown, page_number)
            content_blocks.extend(blocks_from_md)

        return NormalizedPage(
            page_number=page_number,
            content_blocks=content_blocks,
            raw_markdown=raw_markdown,
            raw_html=raw_html,
        )

    def normalize_document(
        self,
        pages_data: dict[int, dict[str, Any]],
    ) -> list[NormalizedPage]:
        """
        Normalize all pages of a document.

        Args:
            pages_data: Output from SarvamClient — {page_num: {json, html, markdown}}

        Returns:
            List of NormalizedPage, sorted by page number.
        """
        pages: list[NormalizedPage] = []
        errors: list[str] = []

        for page_num in sorted(pages_data.keys()):
            page_content = pages_data[page_num]
            try:
                page = self.normalize(
                    raw_json=page_content.get("json", {}),
                    page_number=page_num,
                    raw_html=page_content.get("html", ""),
                    raw_markdown=page_content.get("markdown", ""),
                )
                pages.append(page)
            except NormalizationError as e:
                errors.append(f"Page {page_num}: {e}")
                logger.error(f"Normalization failed for page {page_num}: {e}")
                # Still add an empty page to maintain page ordering
                pages.append(NormalizedPage(page_number=page_num))

        if errors:
            logger.warning(
                f"Normalization completed with {len(errors)} errors: "
                f"{errors[:3]}{'...' if len(errors) > 3 else ''}"
            )

        return pages

    # ─── Content Block Extraction ───────────────────────────

    def _extract_content_blocks(
        self, raw: dict, page_number: int
    ) -> list[ContentBlock]:
        """
        Extract content blocks from the JSON dict.
        Tries multiple fallback paths for the block list.
        """
        blocks: list[ContentBlock] = []

        # Find the list of raw blocks — 5 fallback paths
        raw_blocks = self._find_blocks_list(raw)

        if raw_blocks:
            for i, raw_block in enumerate(raw_blocks):
                block = self._parse_single_block(raw_block, page_number)
                if block:
                    blocks.append(block)
        else:
            # No blocks list found — try treating the whole dict as content
            block = self._parse_flat_content(raw, page_number)
            if block:
                blocks.append(block)

        # Also extract any tables that might be at a different path
        tables_from_json = self._extract_tables_from_json(raw, page_number)
        existing_table_count = sum(1 for b in blocks if b.block_type == "table")
        if tables_from_json and existing_table_count == 0:
            blocks.extend(tables_from_json)

        return blocks

    def _find_blocks_list(self, raw: dict) -> list | None:
        """
        Find the list of content blocks in the raw JSON.
        Sarvam Vision puts them in different places across versions.
        """
        # Path 1: raw["blocks"]
        if isinstance(raw.get("blocks"), list):
            return raw["blocks"]

        # Path 2: raw["content_blocks"]
        if isinstance(raw.get("content_blocks"), list):
            return raw["content_blocks"]

        # Path 3: raw["content"]["blocks"]
        if isinstance(raw.get("content"), dict):
            content = raw["content"]
            if isinstance(content.get("blocks"), list):
                return content["blocks"]
            if isinstance(content.get("elements"), list):
                return content["elements"]

        # Path 4: raw["page"]["blocks"]
        if isinstance(raw.get("page"), dict):
            page = raw["page"]
            if isinstance(page.get("blocks"), list):
                return page["blocks"]
            if isinstance(page.get("content"), list):
                return page["content"]

        # Path 5: raw["elements"]
        if isinstance(raw.get("elements"), list):
            return raw["elements"]

        # Path 6: raw["layout"]["blocks"]
        if isinstance(raw.get("layout"), dict):
            layout = raw["layout"]
            if isinstance(layout.get("blocks"), list):
                return layout["blocks"]

        return None

    def _parse_single_block(
        self, raw_block: dict | str, page_number: int
    ) -> ContentBlock | None:
        """Parse a single raw block into a ContentBlock."""
        if isinstance(raw_block, str):
            # Plain text string
            text = raw_block.strip()
            if not text:
                return None
            return ContentBlock(
                block_type="text",
                content_text=text,
                page_number=page_number,
            )

        if not isinstance(raw_block, dict):
            return None

        # Determine block type
        block_type = self._detect_block_type(raw_block)

        if block_type == "table":
            return self._parse_table_block(raw_block, page_number)
        elif block_type == "heading":
            return self._parse_heading_block(raw_block, page_number)
        else:
            return self._parse_text_block(raw_block, page_number, block_type)

    def _detect_block_type(self, raw_block: dict) -> str:
        """Detect the type of a content block from its fields."""
        # Check explicit type field
        block_type = (
            raw_block.get("type")
            or raw_block.get("block_type")
            or raw_block.get("element_type")
            or raw_block.get("category")
            or ""
        ).lower().strip()

        type_map = {
            "table": "table",
            "tabular": "table",
            "grid": "table",
            "heading": "heading",
            "header": "heading",
            "title": "heading",
            "h1": "heading", "h2": "heading", "h3": "heading",
            "h4": "heading", "h5": "heading", "h6": "heading",
            "image": "image",
            "figure": "image",
            "chart": "image",
            "list": "list",
            "bullet": "list",
            "numbered_list": "list",
            "text": "text",
            "paragraph": "text",
            "para": "text",
        }

        if block_type in type_map:
            return type_map[block_type]

        # Heuristic: check for table-like data
        if any(k in raw_block for k in ("rows", "cells", "table_data", "headers", "columns")):
            return "table"

        # Heuristic: check for heading markers
        if raw_block.get("heading_level") or raw_block.get("level"):
            return "heading"

        return "text"

    # ─── Table Parsing ──────────────────────────────────────

    def _parse_table_block(
        self, raw_block: dict, page_number: int
    ) -> ContentBlock | None:
        """Parse a table block into ContentBlock with TableData."""
        table_data = self._extract_table_data(raw_block)
        if not table_data:
            return None

        # Also try to get the HTML representation
        table_html = (
            raw_block.get("html")
            or raw_block.get("table_html")
            or raw_block.get("rendered_html")
            or ""
        )

        return ContentBlock(
            block_type="table",
            table_data=table_data,
            table_html=table_html,
            content_text=self._table_to_text(table_data),
            confidence=float(raw_block.get("confidence", 1.0)),
            bounding_box=raw_block.get("bbox") or raw_block.get("bounding_box"),
            page_number=page_number,
        )

    def _extract_table_data(self, raw: dict) -> TableData | None:
        """
        Extract table data from a raw block, trying multiple
        possible structures that Sarvam Vision might output.
        """
        headers: list[list[str]] = []
        rows: list[list[str]] = []
        merged_cells: list[MergedCell] = []
        footnotes: list[str] = []

        # ── Try to find the table data ──

        # Path 1: raw["table_data"] or raw["data"]
        table_src = raw.get("table_data") or raw.get("data") or raw

        if isinstance(table_src, dict):
            # Extract headers
            headers = self._extract_headers(table_src)
            # Extract rows
            rows = self._extract_rows(table_src)
            # Extract merged cells
            merged_cells = self._extract_merged_cells(table_src)

        # Path 2: raw["rows"] is a list of lists (simple grid)
        elif isinstance(table_src, list):
            for row in table_src:
                if isinstance(row, list):
                    rows.append([self._cell_to_str(cell) for cell in row])

        # Path 3: raw["cells"] is a flat list of cell objects
        if not rows and isinstance(raw.get("cells"), list):
            rows, headers = self._cells_list_to_grid(raw["cells"])

        # If we still have no data, this isn't a valid table
        if not rows and not headers:
            return None

        # Extract footnote markers from all cells
        all_cells = []
        for row in headers:
            all_cells.extend(row)
        for row in rows:
            all_cells.extend(row)
        footnotes = self._find_footnotes_in_cells(all_cells)

        # Build the canonical TableData
        num_cols = max(
            (max((len(r) for r in headers), default=0)),
            (max((len(r) for r in rows), default=0)),
        )

        return TableData(
            headers=headers,
            rows=rows,
            merged_cells=merged_cells,
            footnotes=footnotes,
            num_columns=num_cols,
            num_rows=len(rows),
        )

    def _extract_headers(self, table_src: dict) -> list[list[str]]:
        """Extract header rows from various possible field names."""
        headers: list[list[str]] = []

        # Try different field names
        raw_headers = (
            table_src.get("headers")
            or table_src.get("header")
            or table_src.get("column_headers")
            or table_src.get("head")
        )

        if raw_headers is None:
            return headers

        if isinstance(raw_headers, list):
            if len(raw_headers) == 0:
                return headers

            # Check if it's a list of lists (multi-level headers)
            if isinstance(raw_headers[0], list):
                for header_row in raw_headers:
                    headers.append([self._cell_to_str(cell) for cell in header_row])
            elif isinstance(raw_headers[0], dict):
                # List of header cell objects
                headers.append([self._cell_to_str(cell) for cell in raw_headers])
            elif isinstance(raw_headers[0], str):
                # Simple list of strings
                headers.append(raw_headers)
            else:
                headers.append([str(h) for h in raw_headers])

        return headers

    def _extract_rows(self, table_src: dict) -> list[list[str]]:
        """Extract data rows from various possible field names."""
        rows: list[list[str]] = []

        raw_rows = (
            table_src.get("rows")
            or table_src.get("body")
            or table_src.get("data_rows")
            or table_src.get("data")
        )

        if raw_rows is None:
            return rows

        if isinstance(raw_rows, list):
            for raw_row in raw_rows:
                if isinstance(raw_row, list):
                    rows.append([self._cell_to_str(cell) for cell in raw_row])
                elif isinstance(raw_row, dict):
                    # Row as dict with "cells" key
                    cells = raw_row.get("cells") or raw_row.get("values") or []
                    if isinstance(cells, list):
                        rows.append([self._cell_to_str(c) for c in cells])
                    else:
                        # Row dict where values are the cells
                        rows.append([self._cell_to_str(v) for v in raw_row.values()])

        return rows

    def _extract_merged_cells(self, table_src: dict) -> list[MergedCell]:
        """Extract merged cell information."""
        merged: list[MergedCell] = []

        raw_merged = (
            table_src.get("merged_cells")
            or table_src.get("merges")
            or table_src.get("spans")
        )

        if not isinstance(raw_merged, list):
            return merged

        for item in raw_merged:
            if isinstance(item, dict):
                try:
                    merged.append(MergedCell(
                        row_start=item.get("row_start", item.get("r1", 0)),
                        row_end=item.get("row_end", item.get("r2", 0)),
                        col_start=item.get("col_start", item.get("c1", 0)),
                        col_end=item.get("col_end", item.get("c2", 0)),
                        value=self._cell_to_str(item.get("value", "")),
                    ))
                except (TypeError, ValueError):
                    continue

        return merged

    def _cells_list_to_grid(
        self, cells: list
    ) -> tuple[list[list[str]], list[list[str]]]:
        """
        Convert a flat list of cell objects (each with row/col indexes)
        into a proper grid.
        """
        if not cells:
            return [], []

        # Find grid dimensions
        max_row = 0
        max_col = 0
        cell_map: dict[tuple[int, int], str] = {}

        for cell in cells:
            if not isinstance(cell, dict):
                continue
            row = cell.get("row", cell.get("row_index", cell.get("r", 0)))
            col = cell.get("col", cell.get("col_index", cell.get("c", 0)))
            value = self._cell_to_str(cell.get("value", cell.get("text", "")))

            cell_map[(row, col)] = value
            max_row = max(max_row, row)
            max_col = max(max_col, col)

        # Build grid
        grid: list[list[str]] = []
        for r in range(max_row + 1):
            row = [cell_map.get((r, c), "") for c in range(max_col + 1)]
            grid.append(row)

        # First row is typically header
        if grid:
            return grid[1:], [grid[0]]

        return [], []

    # ─── Heading / Text Parsing ─────────────────────────────

    def _parse_heading_block(
        self, raw_block: dict, page_number: int
    ) -> ContentBlock | None:
        """Parse a heading block."""
        text = self._extract_text(raw_block)
        if not text:
            return None

        level = (
            raw_block.get("heading_level")
            or raw_block.get("level")
            or raw_block.get("depth")
            or 1
        )

        # Normalize heading level string like "h2" → 2
        if isinstance(level, str):
            match = re.search(r"(\d+)", str(level))
            level = int(match.group(1)) if match else 1

        return ContentBlock(
            block_type="heading",
            content_text=text.strip(),
            heading_level=min(max(int(level), 1), 6),
            confidence=float(raw_block.get("confidence", 1.0)),
            bounding_box=raw_block.get("bbox") or raw_block.get("bounding_box"),
            page_number=page_number,
        )

    def _parse_text_block(
        self, raw_block: dict, page_number: int, block_type: str = "text"
    ) -> ContentBlock | None:
        """Parse a generic text or list block."""
        text = self._extract_text(raw_block)
        if not text:
            return None

        return ContentBlock(
            block_type=block_type if block_type in ("text", "list", "image") else "text",
            content_text=text.strip(),
            confidence=float(raw_block.get("confidence", 1.0)),
            bounding_box=raw_block.get("bbox") or raw_block.get("bounding_box"),
            page_number=page_number,
        )

    def _parse_flat_content(
        self, raw: dict, page_number: int
    ) -> ContentBlock | None:
        """
        Last resort: treat the whole dict as a single text block
        by extracting any text-like fields.
        """
        text = self._extract_text(raw)
        if text:
            return ContentBlock(
                block_type="text",
                content_text=text.strip(),
                page_number=page_number,
            )
        return None

    # ─── HTML / Markdown Fallback ───────────────────────────

    def _extract_from_html(
        self, html: str, page_number: int
    ) -> list[ContentBlock]:
        """
        Fallback: extract content blocks from raw HTML
        when JSON extraction yields nothing.
        """
        blocks: list[ContentBlock] = []

        if not html.strip():
            return blocks

        # Extract tables from HTML
        table_pattern = re.compile(r"<table[^>]*>(.*?)</table>", re.DOTALL | re.IGNORECASE)
        tables = table_pattern.findall(html)

        for table_html in tables:
            table_data = self._parse_html_table(table_html)
            if table_data and (table_data.rows or table_data.headers):
                blocks.append(ContentBlock(
                    block_type="table",
                    table_data=table_data,
                    table_html=f"<table>{table_html}</table>",
                    content_text=self._table_to_text(table_data),
                    page_number=page_number,
                ))

        # Extract remaining text (strip all HTML tags)
        text_only = re.sub(r"<table[^>]*>.*?</table>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text_only = re.sub(r"<[^>]+>", " ", text_only)
        text_only = re.sub(r"\s+", " ", text_only).strip()

        if text_only:
            blocks.append(ContentBlock(
                block_type="text",
                content_text=text_only,
                page_number=page_number,
            ))

        return blocks

    def _extract_from_markdown(
        self, markdown: str, page_number: int
    ) -> list[ContentBlock]:
        """
        Fallback: extract content blocks from raw Markdown.
        """
        blocks: list[ContentBlock] = []

        if not markdown.strip():
            return blocks

        # Split into lines and detect tables (lines with | separators)
        lines = markdown.split("\n")
        current_text: list[str] = []
        current_table: list[str] = []
        in_table = False

        for line in lines:
            is_table_line = "|" in line and line.strip().startswith("|")
            is_separator = bool(re.match(r"^\s*\|[\s\-:|]+\|\s*$", line))

            if is_table_line or is_separator:
                # Flush any pending text
                if current_text and not in_table:
                    text = "\n".join(current_text).strip()
                    if text:
                        blocks.append(ContentBlock(
                            block_type="text",
                            content_text=text,
                            page_number=page_number,
                        ))
                    current_text = []

                in_table = True
                if not is_separator:
                    current_table.append(line)
            else:
                # Flush any pending table
                if in_table and current_table:
                    table_data = self._parse_markdown_table(current_table)
                    if table_data:
                        blocks.append(ContentBlock(
                            block_type="table",
                            table_data=table_data,
                            content_text=self._table_to_text(table_data),
                            page_number=page_number,
                        ))
                    current_table = []
                    in_table = False

                # Check for headings
                heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
                if heading_match:
                    if current_text:
                        text = "\n".join(current_text).strip()
                        if text:
                            blocks.append(ContentBlock(
                                block_type="text",
                                content_text=text,
                                page_number=page_number,
                            ))
                        current_text = []

                    blocks.append(ContentBlock(
                        block_type="heading",
                        content_text=heading_match.group(2).strip(),
                        heading_level=len(heading_match.group(1)),
                        page_number=page_number,
                    ))
                else:
                    current_text.append(line)

        # Flush remaining
        if current_table:
            table_data = self._parse_markdown_table(current_table)
            if table_data:
                blocks.append(ContentBlock(
                    block_type="table",
                    table_data=table_data,
                    content_text=self._table_to_text(table_data),
                    page_number=page_number,
                ))

        if current_text:
            text = "\n".join(current_text).strip()
            if text:
                blocks.append(ContentBlock(
                    block_type="text",
                    content_text=text,
                    page_number=page_number,
                ))

        return blocks

    # ─── Utility Methods ────────────────────────────────────

    def _extract_text(self, raw_block: dict) -> str:
        """Extract text content from a block dict, trying multiple field names."""
        for key in ("text", "content", "content_text", "value", "body", "paragraph",
                     "raw_text", "extracted_text", "ocr_text"):
            val = raw_block.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
            elif isinstance(val, dict):
                # Nested content: try "text" inside
                inner = val.get("text") or val.get("value") or val.get("content")
                if isinstance(inner, str) and inner.strip():
                    return inner.strip()
        return ""

    @staticmethod
    def _cell_to_str(cell: Any) -> str:
        """Convert a table cell (which could be str, dict, int, etc.) to a string."""
        if cell is None:
            return ""
        if isinstance(cell, str):
            return cell.strip()
        if isinstance(cell, (int, float)):
            return str(cell)
        if isinstance(cell, dict):
            return str(
                cell.get("value")
                or cell.get("text")
                or cell.get("content")
                or ""
            ).strip()
        return str(cell).strip()

    @staticmethod
    def _table_to_text(table: TableData) -> str:
        """Convert a TableData to a simple text representation."""
        lines = []
        for header_row in table.headers:
            lines.append(" | ".join(header_row))
        if table.headers:
            lines.append("-" * 40)
        for row in table.rows:
            lines.append(" | ".join(row))
        return "\n".join(lines)

    def _find_footnotes_in_cells(self, cells: list[str]) -> list[str]:
        """Find footnote markers in a list of cell text strings."""
        footnotes: set[str] = set()
        patterns = [
            r"\((\d+)\)",                              # (1), (2)
            r"\(([a-z])\)",                            # (a), (b)
            r"(\*{1,3})",                              # *, **, ***
            r"(?:Note|note)\s+(\d+)",                  # Note 5
            r"(?:Refer|refer)\s+(?:Schedule|schedule)\s+([IVXLCDM]+|[A-Z])",
            r"(?:See|see)\s+(?:Note|note)\s+(\d+)",   # See Note 3
        ]
        for cell in cells:
            if not cell:
                continue
            for pattern in patterns:
                matches = re.findall(pattern, cell)
                for m in matches:
                    footnotes.add(m.strip())
        return sorted(footnotes)

    def _extract_tables_from_json(
        self, raw: dict, page_number: int
    ) -> list[ContentBlock]:
        """
        Look for tables at alternative JSON paths that might not be
        inside the main blocks list.
        """
        blocks: list[ContentBlock] = []

        # Path: raw["tables"]
        raw_tables = raw.get("tables") or raw.get("table_list")
        if isinstance(raw_tables, list):
            for i, raw_table in enumerate(raw_tables):
                if isinstance(raw_table, dict):
                    table_data = self._extract_table_data(raw_table)
                    if table_data:
                        blocks.append(ContentBlock(
                            block_type="table",
                            table_data=table_data,
                            table_html=raw_table.get("html", ""),
                            content_text=self._table_to_text(table_data),
                            page_number=page_number,
                        ))

        return blocks

    def _parse_html_table(self, table_inner_html: str) -> TableData | None:
        """
        Simple HTML table parser (no BeautifulSoup dependency).
        Extracts rows from <tr> tags and cells from <td>/<th> tags.
        """
        headers: list[list[str]] = []
        rows: list[list[str]] = []

        # Find all <tr> rows
        tr_pattern = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
        cell_pattern = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", re.DOTALL | re.IGNORECASE)

        for tr_match in tr_pattern.finditer(table_inner_html):
            tr_content = tr_match.group(1)
            cells = []
            is_header = "<th" in tr_content.lower()

            for cell_match in cell_pattern.finditer(tr_content):
                cell_text = re.sub(r"<[^>]+>", "", cell_match.group(1)).strip()
                cells.append(cell_text)

            if cells:
                if is_header:
                    headers.append(cells)
                else:
                    rows.append(cells)

        if not headers and not rows:
            return None

        num_cols = max(
            max((len(r) for r in headers), default=0),
            max((len(r) for r in rows), default=0),
        )

        return TableData(
            headers=headers,
            rows=rows,
            num_columns=num_cols,
            num_rows=len(rows),
            footnotes=self._find_footnotes_in_cells(
                [c for row in headers + rows for c in row]
            ),
        )

    def _parse_markdown_table(self, table_lines: list[str]) -> TableData | None:
        """Parse Markdown table lines into TableData."""
        if not table_lines:
            return None

        rows: list[list[str]] = []
        for line in table_lines:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows.append(cells)

        if not rows:
            return None

        # First row is header
        headers = [rows[0]] if rows else []
        data_rows = rows[1:] if len(rows) > 1 else []

        num_cols = max(len(r) for r in rows) if rows else 0

        return TableData(
            headers=headers,
            rows=data_rows,
            num_columns=num_cols,
            num_rows=len(data_rows),
            footnotes=self._find_footnotes_in_cells(
                [c for row in rows for c in row]
            ),
        )
