from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf

app = FastAPI(title="vittSarathi API")

# Allow connections from the frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {
        "status": "running",
        "message": "FastAPI backend container is active!"
    }

@app.get("/api/stock/{ticker}")
def get_stock_data(ticker: str):
    ticker = ticker.upper().strip()
    
    # Try the raw ticker first
    ticker_obj = yf.Ticker(ticker)
    info = {}
    try:
        info = ticker_obj.info
    except Exception:
        info = {}
        
    # If the ticker has no substantial information and doesn't contain a dot,
    # try automatically appending .NS (National Stock Exchange of India)
    if not info or not info.get("marketCap") or not info.get("longName"):
        if "." not in ticker:
            indian_ticker = f"{ticker}.NS"
            try:
                indian_ticker_obj = yf.Ticker(indian_ticker)
                indian_info = indian_ticker_obj.info
                if indian_info and (indian_info.get("marketCap") or indian_info.get("longName")):
                    info = indian_info
                    ticker = indian_ticker
            except Exception:
                pass

    # If still not found or insufficient information, try BSE (.BO)
    if not info or not info.get("marketCap") or not info.get("longName"):
        if "." not in ticker:
            indian_ticker_bse = f"{ticker}.BO"
            try:
                bse_ticker_obj = yf.Ticker(indian_ticker_bse)
                bse_info = bse_ticker_obj.info
                if bse_info and (bse_info.get("marketCap") or bse_info.get("longName")):
                    info = bse_info
                    ticker = indian_ticker_bse
            except Exception:
                pass
                
    # If still no substantial info is retrieved, raise 404
    if not info or (not info.get("marketCap") and not info.get("longName") and not info.get("currentPrice") and not info.get("regularMarketPrice")):
        raise HTTPException(
            status_code=404, 
            detail=f"Stock ticker '{ticker}' not found or no data available. Note: For Indian stocks, try appending .NS (e.g. RELIANCE.NS)."
        )
        
    # Helper functions to convert values safely
    def safe_float(val):
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    def safe_int(val):
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    # Construct clean structured response with all 12 categories
    payload = {
        "symbol": info.get("symbol", ticker),
        "longName": info.get("longName", info.get("shortName", ticker)),
        "currency": info.get("currency", "USD"),
        "currentPrice": safe_float(info.get("currentPrice", info.get("regularMarketPrice"))),
        "summary": info.get("longBusinessSummary", ""),
        "sector": info.get("sector", "N/A"),
        "industry": info.get("industry", "N/A"),
        
        # 1. Valuation
        "peRatio": safe_float(info.get("trailingPE", info.get("forwardPE"))),
        
        # 2. Growth
        "revenueGrowth": safe_float(info.get("revenueGrowth")),
        "earningsGrowth": safe_float(info.get("earningsGrowth")),
        
        # 3. Profitability
        "profitMargin": safe_float(info.get("profitMargins")),
        "roe": safe_float(info.get("returnOnEquity")),
        
        # 4. Financial Health
        "debtToEquity": safe_float(info.get("debtToEquity")),
        
        # 5. Market Sentiment
        "recommendation": info.get("recommendationKey", "N/A"),
        "targetPrice": safe_float(info.get("targetMeanPrice", info.get("targetMedianPrice"))),
        
        # 6. Share Data
        "marketCap": safe_int(info.get("marketCap")),
        "sharesOutstanding": safe_int(info.get("sharesOutstanding")),
        "floatShares": safe_int(info.get("floatShares")),
        
        # 7. Trading Activity
        "volume": safe_int(info.get("volume", info.get("regularMarketVolume"))),
        "averageVolume": safe_int(info.get("averageVolume", info.get("averageVolume10days"))),
        
        # 8. Risk
        "beta": safe_float(info.get("beta")),
        
        # 9. Income
        "dividendYield": safe_float(info.get("dividendYield")),
        "payoutRatio": safe_float(info.get("payoutRatio")),
        
        # 10. Momentum
        "fiftyTwoWeekHigh": safe_float(info.get("fiftyTwoWeekHigh")),
        "fiftyTwoWeekLow": safe_float(info.get("fiftyTwoWeekLow")),
        "fiftyDayAverage": safe_float(info.get("fiftyDayAverage")),
        "twoHundredDayAverage": safe_float(info.get("twoHundredDayAverage")),
        
        # 11. Ownership
        "heldPercentInstitutions": safe_float(info.get("heldPercentInstitutions")),
        "heldPercentInsiders": safe_float(info.get("heldPercentInsiders")),
        
        # 12. Cash Flow
        "freeCashFlow": safe_int(info.get("freeCashFlow"))
    }
    
    return payload
