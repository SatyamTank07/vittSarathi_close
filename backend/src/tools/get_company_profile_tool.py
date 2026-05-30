import yfinance as yf
from langchain_core.tools import tool

@tool
def get_company_profile(ticker: str) -> dict:
    """
    Fetches the company profile for a given stock ticker using yfinance.
    Returns details including ticker, sector, industry, country, exchange, and business_summary.
    """
    ticker_clean = ticker.upper().strip()

    ticker_obj = yf.Ticker(ticker_clean)
    info = {}
    try:
        info = ticker_obj.info
    except Exception:
        pass

    # Fallback for Indian stocks if missing market cap / data
    if not info or not info.get("marketCap"):
        if "." not in ticker_clean:
            for suffix in [".NS", ".BO"]:
                try:
                    alt_obj = yf.Ticker(f"{ticker_clean}{suffix}")
                    alt_info = alt_obj.info
                    if alt_info and alt_info.get("marketCap"):
                        info = alt_info
                        ticker_clean = f"{ticker_clean}{suffix}"
                        break
                except Exception:
                    continue

    return {
        "ticker": info.get("symbol", ticker_clean),
        "company_name": info.get("longName", info.get("shortName", ticker_clean)),
        "sector": info.get("sector", "Unknown"),
        "industry": info.get("industry", "Unknown"),
        "country": info.get("country", "Unknown"),
        "exchange": info.get("exchange", "Unknown"),
        "currency": info.get("currency", "USD"),
        "current_price": info.get("currentPrice", info.get("regularMarketPrice")),
        "business_summary": info.get("longBusinessSummary", "")
    }
