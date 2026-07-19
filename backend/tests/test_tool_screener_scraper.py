"""
Unit tests for the rewritten screener_scraper (httpx + BeautifulSoup).

Mocks HTTP responses instead of LLM agents — no API keys needed.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from src.tools.screener_scraper import (
    scrape_screener,
    DataSource,
    _failure_counts,
    _circuit_open,
    _parse_screener_html,
    _extract_top_ratios,
    _extract_table,
    _clean_cell,
    _to_screener_ticker,
)
from bs4 import BeautifulSoup


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_circuit_breaker():
    """Reset global circuit breaker before each test."""
    _failure_counts.clear()
    _circuit_open.clear()


# ── Sample HTML fragments ─────────────────────────────────────────────

SAMPLE_TOP_RATIOS = """
<ul id="top-ratios">
  <li>
    <span class="name">Market Cap</span>
    <span class="number"><span class="value">5,62,951</span> Cr.</span>
  </li>
  <li>
    <span class="name">Stock P/E</span>
    <span class="number"><span class="value">29.3</span></span>
  </li>
  <li>
    <span class="name">ROCE</span>
    <span class="number"><span class="value">12.5 %</span></span>
  </li>
</ul>
"""

SAMPLE_PL_TABLE = """
<section id="profit-loss">
  <table class="data-table">
    <thead>
      <tr><th></th><th>Mar 2023</th><th>Mar 2024</th><th>Mar 2025</th></tr>
    </thead>
    <tbody>
      <tr><td><button>Sales +</button></td><td>26,385</td><td>33,304</td><td>40,119</td></tr>
      <tr><td>Net Profit</td><td>8,694</td><td>11,508</td><td>14,062</td></tr>
      <tr><td>EPS</td><td>142</td><td>187</td><td>228</td></tr>
    </tbody>
  </table>
</section>
"""

SAMPLE_BS_TABLE = """
<section id="balance-sheet">
  <table class="data-table">
    <thead>
      <tr><th></th><th>Mar 2023</th><th>Mar 2024</th></tr>
    </thead>
    <tbody>
      <tr><td>Total Assets</td><td>2,72,118</td><td>3,41,534</td></tr>
      <tr><td>Borrowings</td><td>1,85,000</td><td>2,30,000</td></tr>
    </tbody>
  </table>
</section>
"""

SAMPLE_CF_TABLE = """
<section id="cash-flow">
  <table class="data-table">
    <thead>
      <tr><th></th><th>Mar 2023</th><th>Mar 2024</th></tr>
    </thead>
    <tbody>
      <tr><td>Cash from Operating Activity</td><td>-15,000</td><td>-20,000</td></tr>
      <tr><td>Cash from Investing Activity</td><td>-5,000</td><td>-6,000</td></tr>
    </tbody>
  </table>
</section>
"""

SAMPLE_QUARTERS = """
<section id="quarters">
  <table class="data-table">
    <thead>
      <tr><th></th><th>Jun 2024</th><th>Sep 2024</th><th>Dec 2024</th></tr>
    </thead>
    <tbody>
      <tr><td>Revenue</td><td>10,500</td><td>11,200</td><td>11,800</td></tr>
      <tr><td>Net Profit</td><td>3,551</td><td>3,950</td><td>4,300</td></tr>
    </tbody>
  </table>
</section>
"""

SAMPLE_RATIOS_HISTORY = """
<section id="ratios">
  <table class="data-table">
    <thead>
      <tr><th></th><th>Mar 2022</th><th>Mar 2023</th><th>Mar 2024</th></tr>
    </thead>
    <tbody>
      <tr><td>ROE %</td><td>18%</td><td>20%</td><td>22%</td></tr>
      <tr><td>Raw PDF</td><td>link</td><td>link</td><td>link</td></tr>
    </tbody>
  </table>
</section>
"""

def _build_full_page(*sections) -> str:
    """Combine HTML sections into a full page."""
    return f"<html><head><title>Test Company - Screener</title></head><body>{''.join(sections)}</body></html>"

FULL_PAGE_HTML = _build_full_page(
    SAMPLE_TOP_RATIOS, SAMPLE_PL_TABLE, SAMPLE_BS_TABLE,
    SAMPLE_CF_TABLE, SAMPLE_QUARTERS, SAMPLE_RATIOS_HISTORY,
)

PARTIAL_PAGE_HTML = _build_full_page(
    SAMPLE_TOP_RATIOS, SAMPLE_PL_TABLE, SAMPLE_BS_TABLE,
    # No cash flow, no quarters
)


# ── Unit Tests: Helpers ───────────────────────────────────────────────

def test_to_screener_ticker():
    assert _to_screener_ticker("BAJFINANCE.NS") == "BAJFINANCE"
    assert _to_screener_ticker("RELIANCE.BO") == "RELIANCE"
    assert _to_screener_ticker("HDFCBANK") == "HDFCBANK"
    assert _to_screener_ticker("  infy.ns  ") == "INFY"


def test_clean_cell():
    assert _clean_cell("26,385") == 26385
    assert _clean_cell("18%") == "18%"
    assert _clean_cell("-") is None
    assert _clean_cell("") is None
    assert _clean_cell("  ") is None
    assert _clean_cell("3.14") == 3.14
    assert _clean_cell("Some Text") == "Some Text"
    assert _clean_cell(None) is None


# ── Unit Tests: BeautifulSoup Extractors ──────────────────────────────

def test_extract_top_ratios():
    soup = BeautifulSoup(SAMPLE_TOP_RATIOS, "html.parser")
    ratios = _extract_top_ratios(soup)
    assert ratios is not None
    assert "Market Cap" in ratios
    assert "Stock P/E" in ratios
    assert ratios["Stock P/E"] == "29.3"


def test_extract_top_ratios_missing():
    soup = BeautifulSoup("<html><body></body></html>", "html.parser")
    assert _extract_top_ratios(soup) is None


def test_extract_table_profit_loss():
    soup = BeautifulSoup(SAMPLE_PL_TABLE, "html.parser")
    result = _extract_table(soup, "profit-loss")
    assert result is not None
    assert result["periods"] == ["Mar 2023", "Mar 2024", "Mar 2025"]
    assert "Sales" in result["rows"]
    assert "Net Profit" in result["rows"]
    assert result["rows"]["EPS"] == [142, 187, 228]


def test_extract_table_skips_raw_pdf():
    soup = BeautifulSoup(SAMPLE_RATIOS_HISTORY, "html.parser")
    result = _extract_table(soup, "ratios")
    assert result is not None
    assert "ROE %" in result["rows"]
    assert "Raw PDF" not in result["rows"]


def test_extract_table_missing():
    soup = BeautifulSoup("<html><body></body></html>", "html.parser")
    assert _extract_table(soup, "profit-loss") is None


def test_extract_table_expandable_rows():
    """Expandable rows with <button>Sales +</button> should parse as 'Sales'."""
    soup = BeautifulSoup(SAMPLE_PL_TABLE, "html.parser")
    result = _extract_table(soup, "profit-loss")
    assert "Sales" in result["rows"]
    # Should NOT have "Sales +" as the label
    assert "Sales +" not in result["rows"]


# ── Unit Tests: Full Page Parsing ─────────────────────────────────────

def test_parse_full_page():
    data = _parse_screener_html(FULL_PAGE_HTML)
    assert data["ratios"] is not None
    assert data["profit_loss"] is not None
    assert data["balance_sheet"] is not None
    assert data["cash_flow"] is not None
    assert data["quarters"] is not None
    assert data["ratios_history"] is not None


def test_parse_partial_page():
    data = _parse_screener_html(PARTIAL_PAGE_HTML)
    assert data["ratios"] is not None
    assert data["profit_loss"] is not None
    assert data["balance_sheet"] is not None
    assert data["cash_flow"] is None  # Missing from partial page
    assert data["quarters"] is None   # Missing from partial page


def test_parse_404_page():
    html = "<html><head><title>Error 404: Page Not Found</title></head><body>Not found</body></html>"
    with pytest.raises(ValueError, match="page_not_found"):
        _parse_screener_html(html)


def test_parse_captcha_page():
    html = "<html><head><title>Just a moment...</title></head><body>Checking browser</body></html>"
    with pytest.raises(ValueError, match="bot_blocked"):
        _parse_screener_html(html)


def test_parse_unrecognized_page():
    html = "<html><head><title>Screener</title></head><body>Some other page</body></html>"
    with pytest.raises(ValueError, match="page_not_recognized"):
        _parse_screener_html(html)


# ── Integration Tests: scrape_screener() ──────────────────────────────

@pytest.mark.asyncio
@patch("src.tools.screener_scraper._fetch_html")
async def test_scrape_success(mock_fetch):
    """Full scrape with all tables → SCREENER_SCRAPED."""
    mock_fetch.return_value = (FULL_PAGE_HTML, "httpx")

    result = await scrape_screener("TCS.NS")

    assert result.ticker == "TCS.NS"
    assert result.data_source == DataSource.SCREENER_SCRAPED
    assert result.error is None
    assert "Market Cap" in result.ratios
    assert result.financials["profit_loss"] is not None
    assert result.financials["balance_sheet"] is not None
    assert result.financials["cash_flow"] is not None
    assert result.quarters is not None
    assert result.ratios_history is not None


@pytest.mark.asyncio
@patch("src.tools.screener_scraper._fetch_html")
async def test_scrape_partial(mock_fetch):
    """Partial scrape (missing cash flow) → PARTIAL."""
    mock_fetch.return_value = (PARTIAL_PAGE_HTML, "httpx")

    result = await scrape_screener("HDFCBANK.NS")

    assert result.data_source == DataSource.PARTIAL
    assert result.financials["cash_flow"] is None
    assert result.financials["profit_loss"] is not None


@pytest.mark.asyncio
@patch("src.tools.screener_scraper._fetch_html")
async def test_scrape_consolidated_fails_base_succeeds(mock_fetch):
    """Consolidated URL returns nothing, base URL works."""
    # First call (consolidated) → None, second call (base) → HTML
    mock_fetch.side_effect = [
        (None, "none"),
        (FULL_PAGE_HTML, "httpx"),
    ]

    result = await scrape_screener("BAJFINANCE.NS")

    assert result.data_source == DataSource.SCREENER_SCRAPED
    assert mock_fetch.call_count == 2


@pytest.mark.asyncio
@patch("src.tools.screener_scraper._fetch_html")
async def test_scrape_both_urls_fail(mock_fetch):
    """Both consolidated and base URLs fail → FAILED."""
    mock_fetch.return_value = (None, "none")

    result = await scrape_screener("INVALID.NS")

    assert result.data_source == DataSource.FAILED
    assert "Could not fetch" in result.error


@pytest.mark.asyncio
@patch("src.tools.screener_scraper._fetch_html")
async def test_scrape_bot_blocked(mock_fetch):
    """Page is a captcha → FAILED with bot_blocked."""
    captcha_html = "<html><head><title>Just a moment...</title></head><body>Checking</body></html>"
    mock_fetch.return_value = (captcha_html, "httpx")

    result = await scrape_screener("TCS.NS")

    assert result.data_source == DataSource.FAILED
    assert "bot_blocked" in result.error


@pytest.mark.asyncio
@patch("src.tools.screener_scraper._fetch_html")
async def test_circuit_breaker(mock_fetch):
    """3 consecutive failures open the circuit breaker."""
    mock_fetch.return_value = (None, "none")

    # Fail 3 times
    for _ in range(3):
        res = await scrape_screener("FAIL")
        assert res.data_source == DataSource.FAILED

    # 4th call should short-circuit without calling _fetch_html
    mock_fetch.reset_mock()
    res4 = await scrape_screener("FAIL")

    assert res4.data_source == DataSource.FAILED
    assert "Circuit breaker open" in res4.error
    mock_fetch.assert_not_called()


@pytest.mark.asyncio
@patch("src.tools.screener_scraper._fetch_html")
async def test_quarters_and_ratios_history(mock_fetch):
    """Verify new fields (quarters, ratios_history) are extracted."""
    mock_fetch.return_value = (FULL_PAGE_HTML, "httpx")

    result = await scrape_screener("BAJFINANCE.NS")

    # Quarters
    assert result.quarters is not None
    assert "Jun 2024" in result.quarters["periods"]
    assert "Revenue" in result.quarters["rows"]

    # Ratios history
    assert result.ratios_history is not None
    assert "Mar 2022" in result.ratios_history["periods"]
    assert "ROE %" in result.ratios_history["rows"]
    assert result.ratios_history["rows"]["ROE %"] == ["18%", "20%", "22%"]
