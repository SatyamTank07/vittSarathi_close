import os
import json
import re
import logging
import asyncio
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

class DataSource(str, Enum):
    SCREENER_SCRAPED = "screener_scraped"
    PARTIAL          = "partial"
    FAILED           = "failed"

@dataclass
class ScreenerResult:
    ticker: str
    ratios: dict
    financials: dict
    data_source: DataSource
    error: Optional[str] = None

logger = logging.getLogger("vittsarathi.tools.screener_scraper")

_failure_counts: dict = {}
_circuit_open: set = set()
FAILURE_THRESHOLD = 3

def _is_circuit_open() -> bool:
    return "screener" in _circuit_open

def _record_failure():
    _failure_counts["screener"] = _failure_counts.get("screener", 0) + 1
    if _failure_counts["screener"] >= FAILURE_THRESHOLD:
        _circuit_open.add("screener")
        logger.warning("[screener_scraper] Circuit breaker OPEN — screener.in scraping disabled for this session")

def _record_success():
    _failure_counts["screener"] = 0
    _circuit_open.discard("screener")

def _to_screener_ticker(ticker: str) -> str:
    """
    Converts exchange-suffixed ticker to Screener.in format.
    HDFCBANK.NS  →  HDFCBANK
    RELIANCE.BO  →  RELIANCE
    """
    return ticker.split(".")[0].upper().strip()

def _get_scraper_llm() -> ChatOpenAI:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip('"').strip("'")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set")
    return ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
        max_tokens=4000,
        api_key=api_key,
    )

def _build_scrape_prompt(ticker: str) -> str:
    return (
        "You are a precise data extraction agent. Your only job is to extract financial data from Screener.in and return it as a JSON object.\n\n"
        "Follow these steps exactly:\n\n"
        f"1. Navigate to this URL: https://www.screener.in/company/{ticker}/consolidated/\n"
        "   If it redirects to standalone, that is fine.\n"
        "2. Wait for the page to fully load.\n"
        "3. Extract ALL ratio values from the top ratios section (usually id=\"top-ratios\"). Get every label and value shown.\n"
        "4. Find the Profit & Loss table (often id=\"profit-loss\"). Extract all column headers (years) and all row data from it.\n"
        "   If you cannot find it by ID, look for the text 'Profit & Loss'.\n"
        "5. Find the Balance Sheet table (often id=\"balance-sheet\"). Extract all column headers and all row data.\n"
        "6. Find the Cash Flow table (often id=\"cash-flow\"). Extract all column headers and all row data.\n"
        "7. Return ONLY a raw JSON object with this exact structure. No markdown. No explanation. No code fences. Just the JSON:\n\n"
        "{\n"
        "  \"ratios\": {\n"
        "    \"Market Cap\": \"value here\",\n"
        "    \"Stock P/E\": \"value here\",\n"
        "    \"Book Value\": \"value here\",\n"
        "    \"Dividend Yield\": \"value here\",\n"
        "    \"ROCE\": \"value here\",\n"
        "    \"ROE\": \"value here\"\n"
        "  },\n"
        "  \"profit_loss\": {\n"
        "    \"years\": [\"Mar 2020\", \"Mar 2021\", ...],\n"
        "    \"rows\": {\n"
        "      \"Sales\": [\"value\", \"value\", ...],\n"
        "      \"Net Profit\": [\"value\", \"value\", ...]\n"
        "    }\n"
        "  },\n"
        "  \"balance_sheet\": {\n"
        "    \"years\": [\"Mar 2020\", \"Mar 2021\", ...],\n"
        "    \"rows\": {\n"
        "      \"Total Assets\": [\"value\", \"value\", ...]\n"
        "    }\n"
        "  },\n"
        "  \"cash_flow\": {\n"
        "    \"years\": [\"Mar 2020\", \"Mar 2021\", ...],\n"
        "    \"rows\": {\n"
        "      \"Cash from Operations\": [\"value\", \"value\", ...]\n"
        "    }\n"
        "  }\n"
        "}\n\n"
        "If a table is not found on the page, set its key to null but continue extracting the rest.\n"
        "If the page does not load or shows an error, return exactly: {\"error\": \"page_load_failed\"}\n"
        "Do not include any text outside the JSON object."
    )

async def scrape_screener(ticker: str) -> ScreenerResult:
    """
    Scrapes Screener.in for the given ticker using the Playwright MCP sidecar.
    Returns a ScreenerResult with data_source indicating quality.
    """

    if _is_circuit_open():
        logger.warning(f"[screener_scraper] Circuit open — skipping scrape for {ticker}")
        return ScreenerResult(
            ticker=ticker,
            ratios={},
            financials={},
            data_source=DataSource.FAILED,
            error="Circuit breaker open: too many consecutive failures"
        )

    screener_ticker = _to_screener_ticker(ticker)
    url = f"https://www.screener.in/company/{screener_ticker}/consolidated/"
    playwright_url = os.environ.get("PLAYWRIGHT_MCP_URL", "http://playwright-mcp:8931/sse")

    logger.info(f"[screener_scraper] Starting scrape for {ticker} → {url}")

    try:
        client = MultiServerMCPClient({
            "playwright": {
                "url": playwright_url,
                "transport": "sse",
                "headers": {"Host": "localhost:8931"}
            }
        })

        prompt = _build_scrape_prompt(ticker)
        tools = await client.get_tools()
        for t in tools:
            t.handle_tool_error = True

        llm = _get_scraper_llm()

        # Use a plain langgraph ReAct agent
        agent = create_react_agent(
            model=llm,
            tools=tools,
            prompt=prompt,
        )

        result = await asyncio.wait_for(
            agent.ainvoke({"messages": [("user", "Start extraction.")]}),
            timeout=90.0
        )

        raw_output = result["messages"][-1].content
        logger.debug(f"[screener_scraper] Raw output: {raw_output[:500]}")

        # Strip markdown code fences if LLM wrapped the JSON
        clean = re.sub(r"```json|```", "", raw_output).strip()

        data = json.loads(clean)

        if "error" in data:
            _record_failure()
            logger.warning(f"[screener_scraper] Page error for {ticker}: {data['error']}")
            return ScreenerResult(
                ticker=ticker,
                ratios={},
                financials={},
                data_source=DataSource.FAILED,
                error=data["error"]
            )

        # Check what we actually got — partial vs full
        financials = {
            "profit_loss":   data.get("profit_loss"),
            "balance_sheet": data.get("balance_sheet"),
            "cash_flow":     data.get("cash_flow"),
        }
        tables_found = sum(1 for v in financials.values() if v is not None)
        data_source = DataSource.SCREENER_SCRAPED if tables_found == 3 else DataSource.PARTIAL

        _record_success()
        logger.info(f"[screener_scraper] Success for {ticker} — tables found: {tables_found}/3 — source: {data_source.value}")

        return ScreenerResult(
            ticker=ticker,
            ratios=data.get("ratios", {}),
            financials=financials,
            data_source=data_source,
            error=None
        )

    except asyncio.TimeoutError:
        _record_failure()
        logger.error(f"[screener_scraper] Timeout scraping {ticker}")
        return ScreenerResult(
            ticker=ticker, ratios={}, financials={},
            data_source=DataSource.FAILED,
            error="Scrape timed out after 90 seconds"
        )

    except json.JSONDecodeError as e:
        _record_failure()
        logger.error(f"[screener_scraper] JSON parse failed for {ticker}: {e}")
        return ScreenerResult(
            ticker=ticker, ratios={}, financials={},
            data_source=DataSource.FAILED,
            error=f"JSON parse error: {str(e)}"
        )

    except Exception as e:
        _record_failure()
        logger.error(f"[screener_scraper] Unexpected error for {ticker}: {e}", exc_info=True)
        return ScreenerResult(
            ticker=ticker, ratios={}, financials={},
            data_source=DataSource.FAILED,
            error=str(e)
        )
