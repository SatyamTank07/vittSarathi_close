import os
import httpx
from typing import List, Optional
from mcp.server.fastmcp import FastMCP

# Initialize the MCP Server
mcp = FastMCP(name="FMP Financial Metrics Server")

def _fetch_fmp_ratios(ticker: str, period: str, limit: int) -> list:
    """Helper to fetch from FMP ratios API."""
    api_key = os.getenv("FMP_API_KEY")
    if not api_key:
        raise ValueError("FMP_API_KEY environment variable is not set.")

    ticker_clean = ticker.upper().strip()
    url = f"https://financialmodelingprep.com/api/v3/ratios/{ticker_clean}"
    params = {"period": period, "limit": limit, "apikey": api_key}

    with httpx.Client() as client:
        response = client.get(url, params=params, timeout=10.0)
        response.raise_for_status()
        data = response.json()
    
    if not data:
        raise ValueError(f"No data found for ticker {ticker_clean}.")
    return data

def _filter_ratios(data: list, keys: list, specific_ratios: Optional[List[str]]) -> list:
    """Helper to filter keys from the response data."""
    results = []
    for item in data:
        ratio_data = {"date": item.get("date"), "period": item.get("period")}
        for key in keys:
            ratio_data[key] = item.get(key)
        
        if specific_ratios:
            filtered_data = {"date": ratio_data["date"], "period": ratio_data["period"]}
            for ratio in specific_ratios:
                if ratio in ratio_data:
                    filtered_data[ratio] = ratio_data[ratio]
            results.append(filtered_data)
        else:
            results.append(ratio_data)
    return results

@mcp.tool()
def calc_profitability_ratios(ticker: str, period: str = "annual", limit: int = 5, specific_ratios: Optional[List[str]] = None) -> dict:
    """
    Calculates profitability ratios to understand how efficiently a company generates profit.
    Returns Gross Margin, Operating Margin, Net Profit Margin, Return on Equity (ROE), and Return on Capital Employed (ROCE) 
    over the specified period and limit.
    """
    try:
        data = _fetch_fmp_ratios(ticker, period, limit)
        keys = ["grossProfitMargin", "operatingProfitMargin", "netProfitMargin", "returnOnEquity", "returnOnCapitalEmployed"]
        return {"ticker": ticker.upper(), "ratios": _filter_ratios(data, keys, specific_ratios)}
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def calc_liquidity_ratios(ticker: str, period: str = "annual", limit: int = 5, specific_ratios: Optional[List[str]] = None) -> dict:
    """
    Calculates liquidity ratios to assess if the company can pay off its short-term debts.
    Returns Current Ratio, Quick Ratio, and Cash Ratio over the specified period and limit.
    """
    try:
        data = _fetch_fmp_ratios(ticker, period, limit)
        keys = ["currentRatio", "quickRatio", "cashRatio"]
        return {"ticker": ticker.upper(), "ratios": _filter_ratios(data, keys, specific_ratios)}
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def calc_solvency_and_risk_ratios(ticker: str, period: str = "annual", limit: int = 5, specific_ratios: Optional[List[str]] = None) -> dict:
    """
    Calculates solvency and risk ratios to evaluate long-term debt burden and structural financial risk.
    Returns Debt-to-Equity (debtEquityRatio), Interest Coverage Ratio (interestCoverage), and Debt-to-Assets (debtRatio).
    """
    try:
        data = _fetch_fmp_ratios(ticker, period, limit)
        keys = ["debtEquityRatio", "interestCoverage", "debtRatio"]
        return {"ticker": ticker.upper(), "ratios": _filter_ratios(data, keys, specific_ratios)}
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def calc_valuation_ratios(ticker: str, period: str = "annual", limit: int = 5, specific_ratios: Optional[List[str]] = None) -> dict:
    """
    Calculates valuation ratios to determine if the stock price is cheap or expensive compared to earnings.
    Returns Price-to-Earnings (priceEarningsRatio), Price-to-Book (priceToBookRatio), 
    EV/EBITDA (enterpriseValueMultiple), and PEG Ratio (priceEarningsToGrowthRatio).
    """
    try:
        data = _fetch_fmp_ratios(ticker, period, limit)
        keys = ["priceEarningsRatio", "priceToBookRatio", "enterpriseValueMultiple", "priceEarningsToGrowthRatio"]
        return {"ticker": ticker.upper(), "ratios": _filter_ratios(data, keys, specific_ratios)}
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def calc_efficiency_ratios(ticker: str, period: str = "annual", limit: int = 5, specific_ratios: Optional[List[str]] = None) -> dict:
    """
    Calculates efficiency ratios to measure how well the company manages its day-to-day assets and inventory.
    Returns Inventory Turnover (inventoryTurnover), Asset Turnover (assetTurnover), 
    and Receivables Turnover (receivablesTurnover).
    """
    try:
        data = _fetch_fmp_ratios(ticker, period, limit)
        keys = ["inventoryTurnover", "assetTurnover", "receivablesTurnover"]
        return {"ticker": ticker.upper(), "ratios": _filter_ratios(data, keys, specific_ratios)}
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def fetch_custom_ratios(ticker: str, ratio_keys: List[str], period: str = "annual", limit: int = 5) -> dict:
    """
    Fetches specific custom financial ratios that are not covered by the standard profitability, liquidity, 
    solvency, valuation, or efficiency tools.
    Provide a list of exact ratio keys (e.g., ["payoutRatio", "effectiveTaxRate", "operatingCashFlowPerShare"]).
    """
    try:
        data = _fetch_fmp_ratios(ticker, period, limit)
        return {"ticker": ticker.upper(), "ratios": _filter_ratios(data, ratio_keys, None)}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    mcp.run()
