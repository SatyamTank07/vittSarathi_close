from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
import yfinance as yf
import traceback
import logging

from src.core.database.connection import get_db
from src.agents.orchestrator.pipeline import (
    run_analysis,
    save_report_to_db,
    _save_session,
)
# Response schemas (DashboardResponse, ChatResponse, PatchResponse, ClarificationResponse)
# are defined in src.api.schemas as the official typed contract. They will be wired 
# into the FastAPI route definition in a future step.
from src.api.schemas import AnalyzeRequest

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


@router.post("/analyze")
async def analyze_stock(request: AnalyzeRequest, db: Session = Depends(get_db)):
    """
    Run the multi-agent analysis pipeline.

    Request body:
        query               — natural language query (required)
        session_id          — prior session ID for chat/patch modes (optional)
        existing_state_hash — MD5 of frontend's current SharedState (optional)

    Returns one of:
        DashboardResponse, ChatResponse, PatchResponse, ClarificationResponse
    """
    try:
        result = await run_analysis(
            user_query=request.query,
            session_id=request.session_id,
            existing_state_hash=request.existing_state_hash,
            db=db,
        )

        # Save report to analysis_reports table
        report_id = save_report_to_db(db, result)
        result["report_id"] = report_id

        # Save/update session for dashboard and patch responses
        response_type = result.get("response_type")
        status = result.get("status")

        if status == "success" and response_type in ("dashboard", "patch"):
            # Reconstruct minimal state object for session save
            # We only need session_id, ticker, company_name,
            # has_existing_dashboard, and shared_state_json
            from src.agents.base.shared_state import SharedState
            try:
                # Must happen before the pop below
                state_for_session = SharedState.model_validate_json(
                    result.get("shared_state_json", "{}")
                )
                state_for_session.has_existing_dashboard = True
                _save_session(db, state_for_session, report_id=report_id)
            except Exception as e:
                logger.warning(f"[route] Session save failed (non-fatal): {e}")

        # Remove the large shared_state_json from the HTTP response
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
