"""
PDF Splitter — splits large PDFs into ≤10-page batches for Sarvam Vision.

Uses PyMuPDF (fitz) for fast, reliable PDF manipulation.
Also computes SHA-256 hash of the original file for deduplication.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import uuid
from pathlib import Path

import fitz  # PyMuPDF

from src.rag.config import SARVAM_MAX_PAGES_PER_JOB, TEMP_DIR

logger = logging.getLogger("vittsarathi.rag.ingestion.pdf_splitter")


class PDFSplitter:
    """
    Splits a PDF into batches of ≤N pages (default 10)
    and computes a SHA-256 hash for the original file.
    """

    def __init__(self, max_pages_per_batch: int = SARVAM_MAX_PAGES_PER_JOB):
        self.max_pages = max_pages_per_batch

    def compute_file_hash(self, pdf_path: str) -> str:
        """
        Compute SHA-256 hash of the entire PDF file.
        Used for deduplication — if a report with the same hash
        already exists in the database, skip re-ingestion.

        Args:
            pdf_path: Absolute path to the PDF file.

        Returns:
            Hex-encoded SHA-256 hash string.
        """
        sha256 = hashlib.sha256()
        file_path = Path(pdf_path)

        if not file_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        with open(file_path, "rb") as f:
            # Read in 8KB chunks to handle large files
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                sha256.update(chunk)

        return sha256.hexdigest()

    def get_page_count(self, pdf_path: str) -> int:
        """Return total number of pages in the PDF."""
        doc = fitz.open(pdf_path)
        count = len(doc)
        doc.close()
        return count

    def split(self, pdf_path: str) -> SplitResult:
        """
        Split a PDF into batches of ≤max_pages pages.

        Args:
            pdf_path: Absolute path to the source PDF.

        Returns:
            SplitResult with batch file paths, page ranges, and metadata.

        Raises:
            FileNotFoundError: If the PDF doesn't exist.
            ValueError: If the PDF has 0 pages or is corrupted.
        """
        source = Path(pdf_path)
        if not source.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        # Create a unique temp directory for this split operation
        job_dir = TEMP_DIR / f"split_{uuid.uuid4().hex[:12]}"
        job_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Splitting PDF: {source.name} → {job_dir}")

        doc = fitz.open(str(source))
        total_pages = len(doc)

        if total_pages == 0:
            doc.close()
            raise ValueError(f"PDF has 0 pages: {pdf_path}")

        file_hash = self.compute_file_hash(pdf_path)
        batches: list[BatchInfo] = []

        # Calculate batch ranges
        for batch_start in range(0, total_pages, self.max_pages):
            batch_end = min(batch_start + self.max_pages, total_pages)
            batch_index = len(batches)

            # Extract pages into a new PDF
            batch_doc = fitz.open()  # Empty document
            batch_doc.insert_pdf(
                doc,
                from_page=batch_start,
                to_page=batch_end - 1,  # fitz is inclusive on to_page
            )

            # Save batch PDF
            batch_filename = f"batch_{batch_index:03d}_p{batch_start + 1}-{batch_end}.pdf"
            batch_path = job_dir / batch_filename
            batch_doc.save(str(batch_path))
            batch_doc.close()

            batch_info = BatchInfo(
                batch_index=batch_index,
                file_path=str(batch_path),
                page_start=batch_start + 1,   # 1-indexed for human readability
                page_end=batch_end,            # 1-indexed, inclusive
                num_pages=batch_end - batch_start,
            )
            batches.append(batch_info)

            logger.info(
                f"  Batch {batch_index}: pages {batch_start + 1}-{batch_end} "
                f"({batch_end - batch_start} pages) → {batch_filename}"
            )

        doc.close()

        result = SplitResult(
            source_path=pdf_path,
            source_filename=source.name,
            file_hash=file_hash,
            total_pages=total_pages,
            num_batches=len(batches),
            batches=batches,
            temp_dir=str(job_dir),
        )

        logger.info(
            f"Split complete: {total_pages} pages → {len(batches)} batches "
            f"(hash: {file_hash[:16]}...)"
        )

        return result

    @staticmethod
    def cleanup(result: "SplitResult") -> None:
        """
        Remove temporary batch files after ingestion is complete.

        Args:
            result: The SplitResult from a previous split() call.
        """
        temp_dir = Path(result.temp_dir)
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned up temp dir: {temp_dir}")


# ─────────────────────────────────────────────────────────────
# Data classes (kept here to avoid circular imports)
# ─────────────────────────────────────────────────────────────

class BatchInfo:
    """Metadata about a single batch (sub-PDF)."""

    __slots__ = ("batch_index", "file_path", "page_start", "page_end", "num_pages")

    def __init__(
        self,
        batch_index: int,
        file_path: str,
        page_start: int,
        page_end: int,
        num_pages: int,
    ):
        self.batch_index = batch_index
        self.file_path = file_path
        self.page_start = page_start    # 1-indexed
        self.page_end = page_end        # 1-indexed, inclusive
        self.num_pages = num_pages

    def __repr__(self):
        return (
            f"<Batch {self.batch_index}: pages {self.page_start}-{self.page_end} "
            f"({self.num_pages}p)>"
        )


class SplitResult:
    """Result of splitting a PDF into batches."""

    __slots__ = (
        "source_path", "source_filename", "file_hash",
        "total_pages", "num_batches", "batches", "temp_dir",
    )

    def __init__(
        self,
        source_path: str,
        source_filename: str,
        file_hash: str,
        total_pages: int,
        num_batches: int,
        batches: list[BatchInfo],
        temp_dir: str,
    ):
        self.source_path = source_path
        self.source_filename = source_filename
        self.file_hash = file_hash
        self.total_pages = total_pages
        self.num_batches = num_batches
        self.batches = batches
        self.temp_dir = temp_dir

    def __repr__(self):
        return (
            f"<SplitResult: {self.source_filename} — "
            f"{self.total_pages} pages → {self.num_batches} batches>"
        )
