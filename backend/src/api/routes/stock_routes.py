from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
import yfinance as yf
import traceback
import logging
from pydantic import BaseModel

from src.core.database.connection import get_db
from src.agents.orchestrator.pipeline import run_analysis, save_report_to_db

router = APIRouter(prefix="/api")
logger = logging.getLogger("vittsarathi.api.stock_routes")

@router.get("/stock/{ticker}")
def get_stock_data(ticker: str):
    ticker = ticker.upper().strip()

    # Try the raw ticker first
    ticker_obj = yf.Ticker(ticker)
    info = {}
    try:
        info = ticker_obj.info
    except Exception:
        info = {}

    # Auto-append .NS for Indian stocks
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

    # Try .BO (BSE)
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

    if not info or (not info.get("marketCap") and not info.get("longName") and not info.get("currentPrice") and not info.get("regularMarketPrice")):
        raise HTTPException(
            status_code=404,
            detail=f"Stock ticker '{ticker}' not found or no data available."
        )

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

    payload = {
        "symbol": info.get("symbol", ticker),
        "longName": info.get("longName", info.get("shortName", ticker)),
        "currency": info.get("currency", "USD"),
        "currentPrice": safe_float(info.get("currentPrice", info.get("regularMarketPrice"))),
        "summary": info.get("longBusinessSummary", ""),
        "sector": info.get("sector", "N/A"),
        "industry": info.get("industry", "N/A"),
        "peRatio": safe_float(info.get("trailingPE", info.get("forwardPE"))),
        "revenueGrowth": safe_float(info.get("revenueGrowth")),
        "earningsGrowth": safe_float(info.get("earningsGrowth")),
        "profitMargin": safe_float(info.get("profitMargins")),
        "roe": safe_float(info.get("returnOnEquity")),
        "debtToEquity": safe_float(info.get("debtToEquity")),
        "recommendation": info.get("recommendationKey", "N/A"),
        "targetPrice": safe_float(info.get("targetMeanPrice", info.get("targetMedianPrice"))),
        "marketCap": safe_int(info.get("marketCap")),
        "sharesOutstanding": safe_int(info.get("sharesOutstanding")),
        "floatShares": safe_int(info.get("floatShares")),
        "volume": safe_int(info.get("volume", info.get("regularMarketVolume"))),
        "averageVolume": safe_int(info.get("averageVolume", info.get("averageVolume10days"))),
        "beta": safe_float(info.get("beta")),
        "dividendYield": safe_float(info.get("dividendYield")),
        "payoutRatio": safe_float(info.get("payoutRatio")),
        "fiftyTwoWeekHigh": safe_float(info.get("fiftyTwoWeekHigh")),
        "fiftyTwoWeekLow": safe_float(info.get("fiftyTwoWeekLow")),
        "fiftyDayAverage": safe_float(info.get("fiftyDayAverage")),
        "twoHundredDayAverage": safe_float(info.get("twoHundredDayAverage")),
        "heldPercentInstitutions": safe_float(info.get("heldPercentInstitutions")),
        "heldPercentInsiders": safe_float(info.get("heldPercentInsiders")),
        "freeCashFlow": safe_int(info.get("freeCashFlow")),
    }

    return payload


class AnalyzeRequest(BaseModel):
    query: str

@router.post("/analyze")
async def analyze_stock(request: AnalyzeRequest, db: Session = Depends(get_db)):
    """
    Run the full multi-agent fundamental analysis pipeline dynamically.
    """
    try:
        result = await run_analysis(request.query)

        # Save to database
        report_id = save_report_to_db(db, result)
        result["report_id"] = report_id

        # Remove the large shared_state_json from the response (it's saved in DB)
        result.pop("shared_state_json", None)

        return result

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"ERROR in analysis pipeline:\n{error_details}")
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}"
        )
