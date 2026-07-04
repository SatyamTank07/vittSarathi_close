"""
Sarvam Vision API Client — async client for document digitization.

Wraps the 3-step async workflow:
    1. Upload file → get presigned URL → upload to storage
    2. Submit job → get job_id
    3. Poll status → download results (ZIP → JSON + HTML/Markdown)

API Docs: https://docs.sarvam.ai
Base URL: https://api.sarvam.ai
Auth: api-subscription-key header
Limit: 10 pages per job
"""

import asyncio
import io
import json
import logging
import zipfile
from pathlib import Path
from typing import Any

import httpx

from src.rag.config import (
    SARVAM_API_KEY,
    SARVAM_BASE_URL,
    SARVAM_LANGUAGE,
    SARVAM_OUTPUT_FORMAT,
    SARVAM_POLL_INTERVAL,
    SARVAM_POLL_TIMEOUT,
)

logger = logging.getLogger("vittsarathi.rag.ingestion.sarvam_client")

# ─────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────


class SarvamAPIError(Exception):
    """Raised when the Sarvam API returns an error."""

    def __init__(self, message: str, status_code: int | None = None, response_body: str = ""):
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(message)


class SarvamTimeoutError(SarvamAPIError):
    """Raised when polling for job completion times out."""
    pass


class SarvamPageLimitError(SarvamAPIError):
    """Raised when the uploaded file exceeds the 10-page limit."""
    pass


# ─────────────────────────────────────────────────────────────
# Client
# ─────────────────────────────────────────────────────────────


class SarvamClient:
    """
    Async client for Sarvam AI Document Digitization API.

    Usage:
        client = SarvamClient()
        result = await client.process_pdf_batch("/path/to/batch.pdf")
        # result = {page_num: {json: ..., html: ..., markdown: ...}}
    """

    def __init__(
        self,
        api_key: str = SARVAM_API_KEY,
        base_url: str = SARVAM_BASE_URL,
        language: str = SARVAM_LANGUAGE,
        output_format: str = SARVAM_OUTPUT_FORMAT,
        poll_interval: int = SARVAM_POLL_INTERVAL,
        poll_timeout: int = SARVAM_POLL_TIMEOUT,
    ):
        if not api_key:
            raise ValueError(
                "SARVAM_API_KEY is not set. "
                "Add it to your .env file or pass it directly."
            )

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.language = language
        self.output_format = output_format
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout

        self._headers = {
            "api-subscription-key": self.api_key,
        }

    # ─── Step 1: Create Job ─────────────────────────────────

    async def create_job(self) -> str:
        """
        Step 1: Create a digitization job.
        
        Returns:
            job_id string.
        """
        job_payload = {
            "job_parameters": {
                "language": self.language,
                "output_format": self.output_format,
            }
        }
        logger.info(f"[Sarvam] Creating job (format={self.output_format})")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/doc-digitization/job/v1",
                headers=self._headers,
                json=job_payload,
            )
            self._check_response(response, "create-job")

            result = response.json()
            job_id = result.get("job_id") or result.get("id") or result.get("request_id")

            if not job_id:
                raise SarvamAPIError(
                    "Could not find job_id in create-job response",
                    response_body=json.dumps(result),
                )

            logger.info(f"[Sarvam] Job created: {job_id}")
            return job_id

    # ─── Step 2 & 3: Get Upload URL & Upload PDF ────────────

    async def upload_file(self, job_id: str, file_path: str) -> bool:
        """
        Step 2: Get a presigned upload URL from Sarvam.
        Step 3: Upload the file to that URL.

        Args:
            job_id: The job ID from create_job().
            file_path: Path to the PDF batch file.

        Returns:
            True if upload succeeds.
        """
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise FileNotFoundError(f"Batch file not found: {file_path}")

        file_name = file_path_obj.name
        logger.info(f"[Sarvam] Uploading {file_name} for job {job_id}")

        async with httpx.AsyncClient(timeout=60.0) as client:
            # Step 2: Get presigned upload URL
            response = await client.post(
                f"{self.base_url}/doc-digitization/job/v1/upload-files",
                headers=self._headers,
                json={"job_id": job_id, "files": [file_name]},
            )
            self._check_response(response, "upload-files")

            upload_info = response.json()
            upload_urls = upload_info.get("upload_urls", {})
            url_entry = upload_urls.get(file_name) or (
                list(upload_urls.values())[0] if upload_urls else None
            )
            
            presigned_url = None
            if isinstance(url_entry, str):
                presigned_url = url_entry
            elif isinstance(url_entry, dict):
                presigned_url = url_entry.get("url") or url_entry.get("file_url")
                if not presigned_url:
                    for v in url_entry.values():
                        if isinstance(v, str) and v.startswith("http"):
                            presigned_url = v
                            break

            if not presigned_url:
                raise SarvamAPIError(
                    "Could not find presigned URL in upload_urls response",
                    response_body=json.dumps(upload_info),
                )

            # Step 3: PUT actual file
            with open(file_path, "rb") as f:
                file_bytes = f.read()

            upload_response = await client.put(
                presigned_url,
                content=file_bytes,
                headers={
                    "Content-Type": "application/pdf",
                    "x-ms-blob-type": "BlockBlob"
                },
            )

            if upload_response.status_code not in (200, 201, 204):
                raise SarvamAPIError(
                    f"File upload failed with status {upload_response.status_code}",
                    status_code=upload_response.status_code,
                    response_body=upload_response.text[:500]
                )

            logger.info(f"[Sarvam] Upload successful for {file_name}")
            return True

    # ─── Step 4: Start Job ──────────────────────────────────

    async def start_job(self, job_id: str) -> bool:
        """
        Step 4: Start processing the uploaded job.
        """
        logger.info(f"[Sarvam] Starting job {job_id}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/doc-digitization/job/v1/{job_id}/start",
                headers=self._headers,
                json={},
            )
            
            # Handle specific error codes if needed
            if response.status_code == 400:
                body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                error_code = body.get("code", "")
                if "max_page_limit" in error_code or "page" in str(body).lower():
                    raise SarvamPageLimitError(
                        f"File exceeds the 10-page limit: {body}",
                        status_code=400,
                    )
                    
            self._check_response(response, "start-job")
            return True

    # ─── Step 5: Poll Status ────────────────────────────────

    async def poll_job(self, job_id: str) -> dict:
        """
        Step 5: Poll job status until completion or timeout.
        """
        logger.info(f"[Sarvam] Polling job {job_id} (timeout={self.poll_timeout}s)")
        elapsed = 0

        async with httpx.AsyncClient(timeout=30.0) as client:
            while elapsed < self.poll_timeout:
                response = await client.get(
                    f"{self.base_url}/doc-digitization/job/v1/{job_id}/status",
                    headers=self._headers,
                )
                self._check_response(response, "poll-job")

                status = response.json()
                job_state = (
                    status.get("job_state")
                    or status.get("status")
                    or status.get("state")
                    or ""
                ).lower()

                page_metrics = status.get("page_metrics", {})
                pages_done = page_metrics.get("pages_processed", "?")
                pages_total = page_metrics.get("total_pages", "?")

                logger.info(
                    f"[Sarvam] Job {job_id}: {job_state} "
                    f"({pages_done}/{pages_total} pages, {elapsed}s elapsed)"
                )

                if job_state in ("completed", "complete", "done", "succeeded", "partiallycompleted"):
                    return status

                if job_state in ("failed", "error", "cancelled"):
                    error_msg = status.get("error", status.get("message", "Unknown error"))
                    raise SarvamAPIError(
                        f"Job {job_id} failed: {error_msg}",
                        response_body=json.dumps(status),
                    )

                await asyncio.sleep(self.poll_interval)
                elapsed += self.poll_interval

        raise SarvamTimeoutError(
            f"Job {job_id} did not complete within {self.poll_timeout}s"
        )

    # ─── Step 6 & 7: Download Results ───────────────────────

    async def download_results(self, job_id: str) -> dict[int, dict[str, Any]]:
        """
        Step 6 & 7: Download and extract the results ZIP for a completed job.
        """
        logger.info(f"[Sarvam] Downloading results for job {job_id}")

        async with httpx.AsyncClient(timeout=120.0) as client:
            # Step 6: Get download URLs
            response = await client.post(
                f"{self.base_url}/doc-digitization/job/v1/{job_id}/download-files",
                headers=self._headers,
                json={},
            )
            self._check_response(response, "download-files")

            download_info = response.json()
            download_urls = download_info.get("download_urls", {})
            
            download_url = None
            for fname, entry in download_urls.items():
                if isinstance(entry, dict):
                    download_url = entry.get("file_url") or entry.get("url")
                elif isinstance(entry, str) and entry.startswith("http"):
                    download_url = entry
                if download_url:
                    break

            if not download_url:
                raise SarvamAPIError(
                    "Could not find download URL in response",
                    response_body=json.dumps(download_info),
                )

            # Step 7: Download the ZIP archive
            zip_response = await client.get(download_url)
            if zip_response.status_code != 200:
                raise SarvamAPIError(
                    f"ZIP download failed: {zip_response.status_code}",
                    status_code=zip_response.status_code,
                )

        # Parse the ZIP archive
        return self._parse_zip(zip_response.content)

    # ─── Convenience: Full Pipeline ─────────────────────────

    async def process_pdf_batch(self, file_path: str) -> dict[int, dict[str, Any]]:
        """
        Full pipeline: create → upload → start → poll → download.
        """
        job_id = await self.create_job()
        await self.upload_file(job_id, file_path)
        await self.start_job(job_id)
        await self.poll_job(job_id)
        results = await self.download_results(job_id)
        return results

    # ─── Internal Helpers ───────────────────────────────────

    def _check_response(self, response: httpx.Response, step: str) -> None:
        """Raise SarvamAPIError if the response indicates an error."""
        if response.status_code >= 400:
            try:
                body = response.json()
                detail = body.get("detail", body.get("message", body.get("error", str(body))))
            except Exception:
                detail = response.text[:500]

            raise SarvamAPIError(
                f"[{step}] API error {response.status_code}: {detail}",
                status_code=response.status_code,
                response_body=response.text[:1000],
            )

    def _parse_zip(self, zip_bytes: bytes) -> dict[int, dict[str, Any]]:
        """
        Parse a Sarvam results ZIP archive into per-page content.

        The ZIP typically contains:
            - A JSON file with structured page-level data
            - HTML or Markdown files for each page (or one combined file)

        Returns:
            Dict keyed by page number (1-indexed).
        """
        results: dict[int, dict[str, Any]] = {}

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            file_list = zf.namelist()
            logger.info(f"[Sarvam] ZIP contains {len(file_list)} files: {file_list}")

            json_data = {}
            html_content = {}
            markdown_content = {}

            for fname in file_list:
                # Skip directories and hidden files
                if fname.endswith("/") or fname.startswith("__") or fname.startswith("."):
                    continue

                content = zf.read(fname).decode("utf-8", errors="replace")
                lower_fname = fname.lower()

                if lower_fname.endswith(".json"):
                    try:
                        parsed = json.loads(content)
                        json_data = self._flatten_json_pages(parsed)
                    except json.JSONDecodeError as e:
                        logger.warning(f"[Sarvam] Failed to parse JSON {fname}: {e}")

                elif lower_fname.endswith(".html") or lower_fname.endswith(".htm"):
                    # Try to detect page number from filename
                    page_num = self._extract_page_num(fname, default=1)
                    html_content[page_num] = content

                elif lower_fname.endswith(".md") or lower_fname.endswith(".markdown"):
                    page_num = self._extract_page_num(fname, default=1)
                    markdown_content[page_num] = content

            # Merge all content types into per-page results
            all_pages = set(json_data.keys()) | set(html_content.keys()) | set(markdown_content.keys())

            if not all_pages:
                # If no page-level data found, create a single page entry
                all_pages = {1}

            for page_num in sorted(all_pages):
                results[page_num] = {
                    "json": json_data.get(page_num, {}),
                    "html": html_content.get(page_num, ""),
                    "markdown": markdown_content.get(page_num, ""),
                }

        logger.info(f"[Sarvam] Parsed {len(results)} pages from ZIP")
        return results

    def _flatten_json_pages(self, parsed: Any) -> dict[int, dict]:
        """
        Extract per-page JSON data from the Sarvam JSON output.
        Handles multiple possible structures since the JSON schema
        varies between API versions.
        """
        pages: dict[int, dict] = {}

        if isinstance(parsed, list):
            # Format: [{page: 1, ...}, {page: 2, ...}]
            for i, item in enumerate(parsed):
                page_num = item.get("page", item.get("page_number", i + 1))
                pages[page_num] = item

        elif isinstance(parsed, dict):
            # Format: {pages: [...]} or {1: {...}, 2: {...}} or flat single page
            if "pages" in parsed:
                return self._flatten_json_pages(parsed["pages"])
            elif "results" in parsed:
                return self._flatten_json_pages(parsed["results"])
            elif "data" in parsed and isinstance(parsed["data"], (list, dict)):
                return self._flatten_json_pages(parsed["data"])
            else:
                # Check if keys are page numbers
                numeric_keys = [k for k in parsed.keys() if str(k).isdigit()]
                if numeric_keys:
                    for k in numeric_keys:
                        pages[int(k)] = parsed[k]
                else:
                    # Single page — treat entire dict as page 1
                    pages[1] = parsed

        return pages

    def _extract_page_num(self, filename: str, default: int = 1) -> int:
        """Try to extract a page number from a filename like 'page_3.html'."""
        import re
        match = re.search(r"(?:page|p)[\s_-]*(\d+)", filename, re.IGNORECASE)
        if match:
            return int(match.group(1))
        # Try just finding any number
        match = re.search(r"(\d+)", filename)
        if match:
            return int(match.group(1))
        return default
