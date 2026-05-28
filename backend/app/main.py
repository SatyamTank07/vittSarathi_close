from dotenv import load_dotenv
load_dotenv()  # Load variables from .env file if it exists

import logging
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
import yfinance as yf
from app.database import engine, get_db
from app import models
from app.agents.pipeline import run_analysis, save_report_to_db
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="vittSarathi API — Multi-Agent Stock Analysis")

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
        "message": "vittSarathi backend is active!",
        "version": "2.0 — Agent Orchestration",
    }


# ═══════════════════════════════════════════════════════════
#  STOCK DATA ENDPOINT (Quick lookup — unchanged)
# ═══════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════
#  MULTI-AGENT ANALYSIS ENDPOINTS
# ═══════════════════════════════════════════════════════════

@app.post("/api/analyze/{ticker}")
async def analyze_stock(ticker: str, db: Session = Depends(get_db)):
    """
    Run the full multi-agent fundamental analysis pipeline.
    
    This triggers:
    1. Orchestrator → fetches data, classifies industry
    2. Quantitative + Qualitative + Risk agents → run in parallel
    3. Synthesizer → cross-references, resolves contradictions, compiles final thesis
    4. Report saved to PostgreSQL
    
    Returns the complete analysis result.
    """
    try:
        result = await run_analysis(ticker)

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
        print(f"ERROR in analysis pipeline:\n{error_details}")
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}"
        )


@app.get("/api/reports")
def get_reports(db: Session = Depends(get_db)):
    """List all past analysis reports (most recent first)."""
    reports = db.query(models.AnalysisReport).order_by(
        models.AnalysisReport.created_at.desc()
    ).all()

    return [
        {
            "id": r.id,
            "ticker": r.ticker,
            "company_name": r.company_name,
            "sector": r.sector,
            "industry": r.industry,
            "investment_verdict": r.investment_verdict,
            "confidence_level": r.confidence_level,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in reports
    ]


@app.get("/api/reports/{report_id}")
def get_report(report_id: str, db: Session = Depends(get_db)):
    """Retrieve a specific analysis report by ID."""
    report = db.query(models.AnalysisReport).filter(
        models.AnalysisReport.id == report_id
    ).first()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    return {
        "id": report.id,
        "ticker": report.ticker,
        "company_name": report.company_name,
        "sector": report.sector,
        "industry": report.industry,
        "investment_verdict": report.investment_verdict,
        "confidence_level": report.confidence_level,
        "report_markdown": report.report_markdown,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


@app.delete("/api/reports/{report_id}")
def delete_report(report_id: str, db: Session = Depends(get_db)):
    """Delete a specific analysis report."""
    report = db.query(models.AnalysisReport).filter(
        models.AnalysisReport.id == report_id
    ).first()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    db.delete(report)
    db.commit()
    return {"message": "Report deleted successfully"}
