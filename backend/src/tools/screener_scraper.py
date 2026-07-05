"""
Screener.in financial data scraper.

Extracts ratios, P&L, balance sheet, cash flow, quarterly results,
and historical ratio trends from Screener.in company pages.

Architecture:
  - Tier 1: httpx direct fetch (fast, free, works because screener.in
    is server-rendered — no client-side JS needed).
  - Tier 2: Playwright MCP browser fallback (if httpx gets blocked by
    bot protection / captcha).
  - All HTML parsing is done in Python via BeautifulSoup — no LLM, no
    JavaScript extraction logic.

See .agents/skills/screener-playwright-extraction/SKILL.md for the full
design rationale and selector reference.
"""

import os
import json
import re
import logging
import asyncio
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Any, Tuple

import httpx
from bs4 import BeautifulSoup, Tag


# ── Data Types ────────────────────────────────────────────────────────

class DataSource(str, Enum):
    SCREENER_SCRAPED = "screener_scraped"
    PARTIAL          = "partial"
    FAILED           = "failed"


@dataclass
class ScreenerResult:
    """Result of a Screener.in scrape attempt."""
    ticker: str
    ratios: dict                            # top-ratios snapshot
    financials: dict                        # {profit_loss, balance_sheet, cash_flow}
    data_source: DataSource
    quarters: Optional[dict] = None         # quarterly results table
    ratios_history: Optional[dict] = None   # historical ratio trends table
    error: Optional[str] = None


# ── Logger ────────────────────────────────────────────────────────────

logger = logging.getLogger("vittsarathi.tools.screener_scraper")


# ── Circuit Breaker ───────────────────────────────────────────────────

_failure_counts: dict = {}
_circuit_open: set = set()
FAILURE_THRESHOLD = 3


def _is_circuit_open() -> bool:
    return "screener" in _circuit_open


def _record_failure():
    _failure_counts["screener"] = _failure_counts.get("screener", 0) + 1
    if _failure_counts["screener"] >= FAILURE_THRESHOLD:
        _circuit_open.add("screener")
        logger.warning(
            "[screener_scraper] Circuit breaker OPEN — "
            "screener.in scraping disabled for this session"
        )


def _record_success():
    _failure_counts["screener"] = 0
    _circuit_open.discard("screener")


# ── Ticker Helpers ────────────────────────────────────────────────────

def _to_screener_ticker(ticker: str) -> str:
    """
    Converts exchange-suffixed ticker to Screener.in slug.
    HDFCBANK.NS  →  HDFCBANK
    RELIANCE.BO  →  RELIANCE
    """
    return ticker.split(".")[0].upper().strip()


# ── HTML Fetching — Tier 1: httpx ─────────────────────────────────────

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


async def _fetch_html_httpx(url: str) -> Optional[str]:
    """
    Fetch HTML directly via httpx with browser-like headers.
    Returns HTML string on success, None on failure.
    """
    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers=_BROWSER_HEADERS,
        ) as client:
            resp = await client.get(url)

            if resp.status_code == 200:
                html = resp.text
                lower = html.lower()
                # Detect bot-protection interstitials
                if "just a moment" in lower or "captcha" in lower:
                    logger.warning(
                        f"[screener_scraper] httpx got captcha/block for {url}"
                    )
                    return None
                logger.info(f"[screener_scraper] httpx fetch OK for {url}")
                return html

            elif resp.status_code == 404:
                logger.info(f"[screener_scraper] httpx got 404 for {url}")
                return None

            else:
                logger.warning(
                    f"[screener_scraper] httpx got {resp.status_code} for {url}"
                )
                return None

    except Exception as e:
        logger.warning(f"[screener_scraper] httpx error for {url}: {e}")
        return None


# ── HTML Fetching — Tier 2: Playwright MCP ────────────────────────────

# Minimal JS to grab section HTML from the browser in ONE call.
# All actual parsing happens in Python — this just ferries HTML back.
_SECTION_GRAB_JS = """() => {
    const s = {};
    ['top-ratios','profit-loss','balance-sheet','cash-flow','quarters','ratios'].forEach(id => {
        const el = document.getElementById(id);
        s[id] = el ? el.outerHTML : null;
    });
    s._title = document.title || '';
    s._url = location.href || '';
    return JSON.stringify(s);
}"""


async def _fetch_sections_playwright(url: str) -> Optional[str]:
    """
    Fetch HTML via Playwright MCP browser (fallback when httpx is blocked).

    Uses exactly ONE browser_navigate + ONE browser_evaluate call to avoid
    the parallel-evaluate race condition that crashes the browser tab.

    Returns a reconstructed HTML string containing only the relevant
    sections, or None on failure.
    """
    from langchain_mcp_adapters.client import MultiServerMCPClient

    playwright_url = os.environ.get(
        "PLAYWRIGHT_MCP_URL", "http://playwright-mcp:8931/sse"
    )

    try:
        client = MultiServerMCPClient({
            "playwright": {
                "url": playwright_url,
                "transport": "sse",
                "headers": {"Host": "localhost:8931"},
            }
        })

        tools = await client.get_tools()
        navigate_tool = next(
            (t for t in tools if t.name == "browser_navigate"), None
        )
        evaluate_tool = next(
            (t for t in tools if t.name == "browser_evaluate"), None
        )

        if not navigate_tool or not evaluate_tool:
            logger.error("[screener_scraper] Playwright MCP tools not found")
            return None

        # Step 1: Navigate (one call)
        nav_result = await navigate_tool.ainvoke({"url": url})
        nav_str = str(nav_result)
        logger.debug(
            f"[screener_scraper] Playwright nav: {nav_str[:300]}"
        )

        if "404" in nav_str or "Page Not Found" in nav_str:
            logger.info(f"[screener_scraper] Playwright got 404 for {url}")
            return None

        # Step 2: Grab section HTML (one call — never more)
        eval_result = await evaluate_tool.ainvoke({
            "element": "sections",
            "target": "body",
            "function": _SECTION_GRAB_JS,
        })

        eval_str = str(eval_result)

        # Parse MCP result envelope — format is:
        #   ### Result\n<value>\n### Ran Playwright code...
        result_match = re.search(
            r"### Result\n(.*?)(?:\n### |\Z)", eval_str, re.DOTALL
        )
        if not result_match:
            logger.error(
                "[screener_scraper] Could not parse Playwright eval result: "
                f"{eval_str[:500]}"
            )
            return None

        raw_json = result_match.group(1).strip()
        sections = json.loads(raw_json)

        # Check page validity
        title = sections.get("_title", "")
        if "404" in title or "not found" in title.lower():
            return None
        if "just a moment" in title.lower() or not title:
            logger.warning(
                "[screener_scraper] Playwright got captcha/empty page"
            )
            return None

        # Reconstruct minimal HTML from extracted sections
        html_parts = ["<html><body>"]
        for sid in [
            "top-ratios", "profit-loss", "balance-sheet",
            "cash-flow", "quarters", "ratios",
        ]:
            section_html = sections.get(sid)
            if section_html:
                html_parts.append(section_html)
        html_parts.append("</body></html>")

        return "\n".join(html_parts)

    except Exception as e:
        logger.error(
            f"[screener_scraper] Playwright error for {url}: {e}",
            exc_info=True,
        )
        return None


# ── Unified Fetch ─────────────────────────────────────────────────────

async def _fetch_html(url: str) -> Tuple[Optional[str], str]:
    """
    Fetch HTML from url.  Tries httpx first, falls back to Playwright.
    Returns (html_or_none, method_used).
    """
    html = await _fetch_html_httpx(url)
    if html:
        return html, "httpx"

    logger.info(
        f"[screener_scraper] httpx failed, trying Playwright for {url}"
    )
    html = await _fetch_sections_playwright(url)
    if html:
        return html, "playwright"

    return None, "none"


# ── Python HTML Parsing ───────────────────────────────────────────────

def _clean_cell(text: str) -> Any:
    """
    Clean a table cell value.
    - Strips whitespace, collapses runs
    - Returns None for empty or '-'
    - Keeps percentage strings as-is ("18%")
    - Parses numbers (strips commas)
    """
    if text is None:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    if text == "" or text == "-":
        return None
    if text.endswith("%"):
        return text
    # Try numeric parse
    num_text = text.replace(",", "")
    try:
        num = float(num_text)
        return int(num) if num == int(num) else num
    except ValueError:
        return text


def _row_label(cell: Tag) -> str:
    """
    Extract row label from a table cell.
    Handles expandable rows where label is wrapped in a <button> with
    a trailing '+'.
    """
    if not cell:
        return ""
    button = cell.find("button")
    raw = (button.get_text() if button else cell.get_text()) or ""
    return re.sub(r"\s+", " ", raw).replace("+", "").strip()


def _extract_top_ratios(soup: BeautifulSoup) -> Optional[dict]:
    """
    Extract the snapshot ratios from #top-ratios.
    This is a <ul> of <li> items with .name / .value children,
    NOT a data table.
    """
    container = soup.select_one("#top-ratios")
    if not container:
        return None

    ratios = {}
    for li in container.select(":scope > li"):
        name_el = li.select_one(".name")
        value_el = li.select_one(".value")
        if name_el and value_el:
            name = name_el.get_text(strip=True)
            value = re.sub(r"\s+", " ", value_el.get_text(strip=True))
            if name:
                ratios[name] = value
    return ratios if ratios else None


def _extract_table(soup: BeautifulSoup, section_id: str) -> Optional[dict]:
    """
    Generic table extractor for Screener.in data tables.

    Works for: profit-loss, balance-sheet, cash-flow, quarters, ratios.
    All these follow the same <section id="..."> > table.data-table
    structure with thead (periods) and tbody (data rows).

    Returns { "periods": [...], "rows": { "label": [values], ... } }
    or None if the section/table isn't on the page.
    """
    section = soup.select_one(f"#{section_id}")
    if not section:
        return None

    table = section.select_one("table.data-table")
    if not table:
        return None

    # ─ Extract period headers ─
    header_cells = table.select("thead tr th")
    headers = [
        re.sub(r"\s+", " ", th.get_text(strip=True)) for th in header_cells
    ]
    # First header cell is typically blank (row-label column) — drop it
    periods = headers[1:] if headers and not headers[0] else headers

    # ─ Extract data rows ─
    rows = {}
    for tr in table.select("tbody tr"):
        cells = tr.select("td")
        if not cells:
            continue
        label = _row_label(cells[0])
        # Skip empty labels and the "Raw PDF" link row
        if not label or label == "Raw PDF":
            continue
        values = [_clean_cell(td.get_text(strip=True)) for td in cells[1:]]
        rows[label] = values

    if not periods and not rows:
        return None

    return {"periods": periods, "rows": rows}


def _is_company_page(soup: BeautifulSoup) -> bool:
    """Check if the page looks like a Screener.in company page."""
    return bool(
        soup.select_one("#top-ratios")
        or soup.select_one("#profit-loss")
        or soup.select_one(".sub-nav-holder")
        or soup.select_one("#quarters")
    )


def _detect_block(soup: BeautifulSoup) -> Optional[str]:
    """Detect if the page is a bot-block, captcha, or error page."""
    title = soup.title.get_text(strip=True) if soup.title else ""
    lower_title = title.lower()

    if "404" in title or "not found" in lower_title:
        return "page_not_found"
    if "just a moment" in lower_title or "captcha" in lower_title:
        return "bot_blocked"
    if "access denied" in lower_title or "forbidden" in lower_title:
        return "bot_blocked"

    return None


def _parse_screener_html(html: str) -> dict:
    """
    Parse Screener.in HTML using BeautifulSoup.

    Returns a dict with keys: ratios, ratios_history, quarters,
    profit_loss, balance_sheet, cash_flow.

    Raises ValueError with a descriptive string if the page is not
    a recognized company page (404, captcha, empty, etc.).
    """
    soup = BeautifulSoup(html, "html.parser")

    # Check for block/error pages
    block = _detect_block(soup)
    if block:
        raise ValueError(block)

    # Check for company page landmarks
    if not _is_company_page(soup):
        body_text = (soup.get_text() or "")[:200]
        raise ValueError(f"page_not_recognized: {body_text}")

    return {
        "ratios":          _extract_top_ratios(soup),
        "ratios_history":  _extract_table(soup, "ratios"),
        "quarters":        _extract_table(soup, "quarters"),
        "profit_loss":     _extract_table(soup, "profit-loss"),
        "balance_sheet":   _extract_table(soup, "balance-sheet"),
        "cash_flow":       _extract_table(soup, "cash-flow"),
    }


# ── Main Entry Point ─────────────────────────────────────────────────

async def scrape_screener(ticker: str) -> ScreenerResult:
    """
    Scrapes Screener.in for the given ticker.

    Uses httpx + BeautifulSoup for parsing (no LLM required).
    Falls back to Playwright MCP if httpx is blocked by bot protection.

    Returns a ScreenerResult with data_source indicating quality:
    - SCREENER_SCRAPED: all 3 main tables found
    - PARTIAL: some data found (common for banks missing cash flow)
    - FAILED: could not fetch or parse the page
    """
    # ─ Circuit breaker ─
    if _is_circuit_open():
        logger.warning(
            f"[screener_scraper] Circuit open — skipping {ticker}"
        )
        return ScreenerResult(
            ticker=ticker,
            ratios={},
            financials={},
            data_source=DataSource.FAILED,
            error="Circuit breaker open: too many consecutive failures",
        )

    screener_ticker = _to_screener_ticker(ticker)

    # ─ Try consolidated first, then base URL ─
    urls_to_try = [
        f"https://www.screener.in/company/{screener_ticker}/consolidated/",
        f"https://www.screener.in/company/{screener_ticker}/",
    ]

    html = None
    fetch_method = "none"

    for url in urls_to_try:
        logger.info(f"[screener_scraper] Trying {url}")
        html, fetch_method = await _fetch_html(url)
        if html:
            break

    if not html:
        _record_failure()
        return ScreenerResult(
            ticker=ticker,
            ratios={},
            financials={},
            data_source=DataSource.FAILED,
            error=(
                "Could not fetch page from screener.in "
                "(both httpx and Playwright failed)"
            ),
        )

    # ─ Parse HTML ─
    try:
        data = _parse_screener_html(html)
    except ValueError as e:
        error_str = str(e)
        _record_failure()
        logger.warning(
            f"[screener_scraper] Parse error for {ticker}: {error_str}"
        )
        return ScreenerResult(
            ticker=ticker,
            ratios={},
            financials={},
            data_source=DataSource.FAILED,
            error=error_str,
        )

    # ─ Build result ─
    ratios = data.get("ratios") or {}
    financials = {
        "profit_loss":   data.get("profit_loss"),
        "balance_sheet": data.get("balance_sheet"),
        "cash_flow":     data.get("cash_flow"),
    }
    quarters = data.get("quarters")
    ratios_history = data.get("ratios_history")

    # ─ Classify completeness ─
    tables_found = sum(1 for v in financials.values() if v is not None)
    if tables_found == 3:
        data_source = DataSource.SCREENER_SCRAPED
    elif tables_found > 0 or ratios:
        data_source = DataSource.PARTIAL
    else:
        data_source = DataSource.FAILED

    _record_success()
    logger.info(
        f"[screener_scraper] Done for {ticker} via {fetch_method} — "
        f"tables: {tables_found}/3, ratios: {len(ratios)}, "
        f"quarters: {'yes' if quarters else 'no'}, "
        f"source: {data_source.value}"
    )

    return ScreenerResult(
        ticker=ticker,
        ratios=ratios,
        financials=financials,
        data_source=data_source,
        quarters=quarters,
        ratios_history=ratios_history,
        error=None,
    )
