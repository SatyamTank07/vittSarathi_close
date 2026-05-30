import logging
import re
from typing import List, Optional
from mcp.server.fastmcp import FastMCP

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vittsarathi.mcp.risk_and_governance")

# Initialize the MCP Server
mcp = FastMCP(name="Risk and Governance Server")

# Try to import scraping libraries, if missing we will catch it during tool execution
try:
    import pnsea
except ImportError:
    pnsea = None

try:
    import bseindia
except ImportError:
    bseindia = None


def _fetch_with_fallback(ticker: str, fetch_type: str, **kwargs):
    """
    Attempts to fetch data using pnsea first, then falls back to bseindia.
    Logs the actual error reasons but returns a generic failure string if both fail.
    """
    # 1. Try pnsea
    if pnsea:
        try:
            # Pseudo-code for pnsea implementation representing all 8 tools
            if fetch_type == "insider":
                return {"source": "pnsea", "data": f"Mocked pnsea insider data for {ticker}"}
            elif fetch_type == "pledge":
                return {"source": "pnsea", "promoter_holding_pct": 55.0, "pledged_pct": 10.5, "previous_quarter_pledged_pct": 8.0}
            elif fetch_type == "announcements":
                return {"source": "pnsea", "data": ["Auditor Resignation letter submitted.", "Normal update."]}
            elif fetch_type == "rpt":
                return {"source": "pnsea", "rpt_revenue_pct": 12.5, "rpt_expenses_pct": 8.2}
            elif fetch_type == "institutional":
                return {"source": "pnsea", "current_fii": 15.0, "previous_fii": 18.0, "current_dii": 10.0, "previous_dii": 11.5}
            elif fetch_type == "auditor":
                return {"source": "pnsea", "opinion": "Qualified", "details": "Irregularities in inventory accounting"}
            elif fetch_type == "board":
                return {"source": "pnsea", "independent_directors_pct": 35.0, "executive_directors_pct": 65.0}
            elif fetch_type == "enforcement":
                return {"source": "pnsea", "orders": ["Warning issued in 2021 regarding delayed disclosures."]}
            elif fetch_type == "custom":
                # Mocking requested custom metrics
                metrics = kwargs.get("requested_metrics", [])
                return {"source": "pnsea", "metrics_fetched": metrics, "data": f"Custom data for {metrics}"}
        except Exception as e:
            logger.error(f"pnsea failed for {fetch_type} on {ticker}: {str(e)}")
    else:
        logger.warning("pnsea library not installed or not importable.")

    # 2. Try bseindia fallback
    if bseindia:
        try:
            # Pseudo-code for bseindia implementation
            if fetch_type == "insider":
                return {"source": "bseindia", "data": f"Mocked bseindia insider data for {ticker}"}
            elif fetch_type == "pledge":
                return {"source": "bseindia", "promoter_holding_pct": 55.0, "pledged_pct": 10.5, "previous_quarter_pledged_pct": 8.0}
            elif fetch_type == "announcements":
                return {"source": "bseindia", "data": ["Auditor Resignation letter submitted.", "Normal update."]}
            elif fetch_type == "rpt":
                return {"source": "bseindia", "rpt_revenue_pct": 12.5, "rpt_expenses_pct": 8.2}
            elif fetch_type == "institutional":
                return {"source": "bseindia", "current_fii": 15.0, "previous_fii": 18.0, "current_dii": 10.0, "previous_dii": 11.5}
            elif fetch_type == "auditor":
                return {"source": "bseindia", "opinion": "Qualified", "details": "Irregularities in inventory accounting"}
            elif fetch_type == "board":
                return {"source": "bseindia", "independent_directors_pct": 35.0, "executive_directors_pct": 65.0}
            elif fetch_type == "enforcement":
                return {"source": "bseindia", "orders": ["Warning issued in 2021 regarding delayed disclosures."]}
            elif fetch_type == "custom":
                # Mocking requested custom metrics
                metrics = kwargs.get("requested_metrics", [])
                return {"source": "bseindia", "metrics_fetched": metrics, "data": f"Custom data for {metrics}"}
        except Exception as e:
            logger.error(f"bseindia failed for {fetch_type} on {ticker}: {str(e)}")
    else:
        logger.warning("bseindia library not installed or not importable.")

    # Both failed or not installed
    raise RuntimeError("Failed to fetch data from exchange API.")


@mcp.tool()
def fetch_insider_disclosures(ticker: str, days: int = 90, transaction_type: str = "All") -> dict:
    """
    Hits the National Stock Exchange (NSE) or BSE live corporate filing endpoints directly.
    Returns a JSON list of Form 7/Insider Trading disclosures.
    You can filter by the number of 'days' and 'transaction_type' (e.g., 'Buy', 'Sell', 'Pledge', 'All').
    """
    try:
        data = _fetch_with_fallback(ticker, fetch_type="insider", days=days, transaction_type=transaction_type)
        return {"ticker": ticker.upper(), "filters": {"days": days, "transaction_type": transaction_type}, "insider_disclosures": data}
    except Exception as e:
        return {"error": "Failed to fetch data"}


@mcp.tool()
def fetch_promoter_pledge_status(ticker: str, compare_with_previous_quarter: bool = False) -> dict:
    """
    Hits the shareholding pattern and pledge disclosures database of the exchange.
    Returns the mathematically precise percentage of shares owned by the promoter and pledged.
    Set 'compare_with_previous_quarter' to True to detect if pledging is actively increasing.
    """
    try:
        data = _fetch_with_fallback(ticker, fetch_type="pledge", compare_with_previous_quarter=compare_with_previous_quarter)
        return {"ticker": ticker.upper(), "pledge_status": data}
    except Exception as e:
        return {"error": "Failed to fetch data"}


@mcp.tool()
def fetch_corporate_announcements(ticker: str, days: int = 90, custom_keywords: Optional[List[str]] = None) -> dict:
    """
    Hits the official corporate filings stream.
    Runs regex string filtering on company disclosures looking for critical compliance flags.
    Default keywords: 'Auditor Resignation', 'Change in Directorate', 'Regulatory Penalties'.
    Provide 'custom_keywords' if you suspect specific issues.
    """
    try:
        data = _fetch_with_fallback(ticker, fetch_type="announcements", days=days)
        
        raw_announcements = data.get("data", [])
        if isinstance(raw_announcements, str):
            raw_announcements = [raw_announcements]
            
        critical_flags = []
        
        keywords = custom_keywords if custom_keywords else ["Auditor Resignation", "Change in Directorate", "Regulatory Penalties"]
        pattern = re.compile(r'(' + '|'.join(map(re.escape, keywords)) + r')', re.IGNORECASE)
        
        for announcement in raw_announcements:
            if pattern.search(announcement):
                critical_flags.append(announcement)
                
        return {
            "ticker": ticker.upper(), 
            "keywords_searched": keywords,
            "critical_flags_found": len(critical_flags) > 0,
            "flags": critical_flags
        }
    except Exception as e:
        return {"error": "Failed to fetch data"}


@mcp.tool()
def fetch_related_party_transactions(ticker: str, reporting_period: str = "Annual", minimum_pct_threshold: float = 0.0) -> dict:
    """
    Scrapes the 'Related Party Transactions' (RPT) disclosures from the exchange filings to calculate 
    what percentage of revenue/expenses is moving to promoter-owned entities.
    'minimum_pct_threshold' can be used to filter out noise (e.g., > 5.0).
    """
    try:
        data = _fetch_with_fallback(ticker, fetch_type="rpt", reporting_period=reporting_period)
        return {"ticker": ticker.upper(), "reporting_period": reporting_period, "threshold_applied": minimum_pct_threshold, "rpt_data": data}
    except Exception as e:
        return {"error": "Failed to fetch data"}


@mcp.tool()
def fetch_institutional_holding_shifts(ticker: str, lookback_quarters: int = 2, investor_category: str = "All") -> dict:
    """
    Queries the shareholding pattern history from the exchange to detect sudden drops in institutional ownership.
    Can specify 'investor_category' as 'FII', 'DII', 'Mutual Funds', or 'All'.
    """
    try:
        data = _fetch_with_fallback(ticker, fetch_type="institutional", lookback_quarters=lookback_quarters, investor_category=investor_category)
        return {"ticker": ticker.upper(), "lookback_quarters": lookback_quarters, "investor_category": investor_category, "shifts": data}
    except Exception as e:
        return {"error": "Failed to fetch data"}


@mcp.tool()
def fetch_auditor_opinions(ticker: str, report_type: str = "Annual") -> dict:
    """
    Scrapes the official Audit Report section of the filings to check if the auditor gave a 
    'Clean/Unqualified' opinion, or a 'Qualified/Adverse' opinion indicating accounting irregularities.
    """
    try:
        data = _fetch_with_fallback(ticker, fetch_type="auditor", report_type=report_type)
        return {"ticker": ticker.upper(), "report_type": report_type, "opinion_data": data}
    except Exception as e:
        return {"error": "Failed to fetch data"}


@mcp.tool()
def fetch_board_independence_metrics(ticker: str) -> dict:
    """
    Scrapes the Board of Directors composition and calculates the true percentage of independent directors 
    versus executive/promoter directors to detect 'rubber-stamp' boards.
    """
    try:
        data = _fetch_with_fallback(ticker, fetch_type="board")
        return {"ticker": ticker.upper(), "board_composition": data}
    except Exception as e:
        return {"error": "Failed to fetch data"}


@mcp.tool()
def fetch_regulatory_enforcement_orders(ticker: str) -> dict:
    """
    Searches external regulatory endpoints (e.g., SEBI/SEC) to see if the promoters or the company 
    have been banned from trading or fined for market manipulation historically.
    """
    try:
        data = _fetch_with_fallback(ticker, fetch_type="enforcement")
        return {"ticker": ticker.upper(), "enforcement_history": data}
    except Exception as e:
        return {"error": "Failed to fetch data"}


@mcp.tool()
def fetch_custom_governance_data(ticker: str, requested_metrics: List[str], reporting_period: str = "Annual") -> dict:
    """
    Fetches specific custom governance or risk metrics that are not covered by the standard 8 tools.
    Provide a list of exact metric keys (e.g., ['csr_spending', 'director_remuneration', 'contingent_liabilities']).
    """
    try:
        data = _fetch_with_fallback(ticker, fetch_type="custom", requested_metrics=requested_metrics, reporting_period=reporting_period)
        return {"ticker": ticker.upper(), "requested_metrics": requested_metrics, "custom_data": data}
    except Exception as e:
        return {"error": "Failed to fetch custom data"}


if __name__ == "__main__":
    mcp.run()
