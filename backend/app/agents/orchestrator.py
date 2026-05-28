"""
Agent 1: The Orchestrator (The Managing Director)

Responsibilities:
- Fetch stock data via yfinance
- Identify company industry/sector
- Generate sector-specific instructions for sub-agents
- Create and populate the SharedState
"""

import logging
import yfinance as yf
from app.agents.base_agent import BaseAgent
from app.agents.shared_state import SharedState

logger = logging.getLogger("vittsarathi.agents.orchestrator")


# Industry-specific analysis instructions
INDUSTRY_TEMPLATES = {
    "banking": {
        "quantitative_focus": "Focus on Net Interest Margin (NIM), Non-Performing Assets (NPA/GNPA ratio), Capital Adequacy Ratio (CAR), CASA ratio, Cost-to-Income ratio, and Return on Assets. Credit growth trajectory is critical.",
        "qualitative_focus": "Evaluate branch network reach, digital banking adoption, asset quality management discipline, and regulatory compliance track record.",
        "risk_focus": "Check for rising NPAs, exposure to stressed sectors, asset-liability mismatch, and RBI regulatory actions or penalties.",
    },
    "technology": {
        "quantitative_focus": "Focus on Revenue per Employee, EBITDA margins, order book/deal pipeline, client concentration (top 5 client revenue %), and attrition rate impact on costs.",
        "qualitative_focus": "Evaluate digital transformation capabilities, cloud/AI adoption strategy, client diversification, and ability to move up the value chain from body-shopping to consulting.",
        "risk_focus": "Check for visa regulation risks, currency hedging effectiveness, client concentration risk, and talent retention challenges.",
    },
    "fmcg": {
        "quantitative_focus": "Focus on Volume Growth vs Price Growth decomposition, Gross Margin trends (raw material impact), Distribution reach metrics, and Market Share trajectory.",
        "qualitative_focus": "Evaluate brand power (pricing power test), rural vs urban penetration, new product pipeline, and premiumization strategy.",
        "risk_focus": "Check for commodity price volatility impact, competitive intensity from D2C brands, regulatory risks (FSSAI), and distribution disruption risks.",
    },
    "pharma": {
        "quantitative_focus": "Focus on R&D spend as % of revenue, ANDA pipeline strength, US FDA inspection track record, API vs Formulations revenue mix, and gross margin trends.",
        "qualitative_focus": "Evaluate CRAMS/CDMO opportunity pipeline, biosimilar strategy, domestic market brand strength, and backward integration into APIs.",
        "risk_focus": "Check for FDA warning letters, price erosion in US generics, patent cliffs, and single-facility concentration risk.",
    },
    "default": {
        "quantitative_focus": "Analyze revenue growth trajectory, profit margin expansion/contraction, return ratios (ROE, ROCE), debt levels, and valuation multiples (PE, PB, EV/EBITDA).",
        "qualitative_focus": "Evaluate competitive positioning, management track record, capital allocation discipline, and industry tailwinds/headwinds.",
        "risk_focus": "Check for governance red flags, promoter pledge data, auditor changes, related-party transactions, and cyclical risks.",
    },
}


def _classify_industry(sector: str, industry: str) -> str:
    """Map yfinance sector/industry to our template keys."""
    sector_lower = (sector or "").lower()
    industry_lower = (industry or "").lower()

    if any(kw in sector_lower or kw in industry_lower for kw in ["bank", "financial services", "insurance"]):
        return "banking"
    if any(kw in sector_lower or kw in industry_lower for kw in ["technology", "software", "information"]):
        return "technology"
    if any(kw in sector_lower or kw in industry_lower for kw in ["consumer", "fmcg", "household", "food", "beverage"]):
        return "fmcg"
    if any(kw in sector_lower or kw in industry_lower for kw in ["pharma", "drug", "healthcare", "biotech"]):
        return "pharma"
    return "default"


def _fetch_stock_data(ticker: str) -> dict:
    """Fetch stock data using yfinance with NSE/BSE fallback for Indian stocks."""
    ticker_clean = ticker.upper().strip()

    ticker_obj = yf.Ticker(ticker_clean)
    info = {}
    try:
        info = ticker_obj.info
    except Exception:
        info = {}

    # Try .NS (NSE) if no data
    if not info or not info.get("marketCap"):
        if "." not in ticker_clean:
            try:
                ns_obj = yf.Ticker(f"{ticker_clean}.NS")
                ns_info = ns_obj.info
                if ns_info and ns_info.get("marketCap"):
                    info = ns_info
                    ticker_clean = f"{ticker_clean}.NS"
            except Exception:
                pass

    # Try .BO (BSE) if still no data
    if not info or not info.get("marketCap"):
        if "." not in ticker_clean:
            try:
                bo_obj = yf.Ticker(f"{ticker_clean}.BO")
                bo_info = bo_obj.info
                if bo_info and bo_info.get("marketCap"):
                    info = bo_info
                    ticker_clean = f"{ticker_clean}.BO"
            except Exception:
                pass

    if not info or not info.get("marketCap"):
        raise ValueError(f"No data found for ticker '{ticker}'. Try appending .NS or .BO for Indian stocks.")

    return info


class OrchestratorAgent(BaseAgent):
    """Agent 1: The Managing Director — fetches data, classifies, delegates."""

    agent_name = "orchestrator"
    model = "gpt-4o-mini"

    async def execute(self, state: SharedState = None, ticker: str = None) -> SharedState:
        """
        Create and populate the SharedState from a raw ticker symbol.
        
        This agent doesn't need an existing state — it creates one.
        """
        if not ticker:
            raise ValueError("Orchestrator requires a ticker symbol.")

        logger.info(f"[orchestrator] Starting analysis for {ticker}")

        # 1. Fetch raw stock data
        info = _fetch_stock_data(ticker)

        # 2. Extract key fields
        company_name = info.get("longName", info.get("shortName", ticker))
        sector = info.get("sector", "Unknown")
        industry = info.get("industry", "Unknown")
        currency = info.get("currency", "USD")
        current_price = info.get("currentPrice", info.get("regularMarketPrice"))
        summary = info.get("longBusinessSummary", "")

        # 3. Classify industry and get specialized instructions
        industry_key = _classify_industry(sector, industry)
        instructions = INDUSTRY_TEMPLATES.get(industry_key, INDUSTRY_TEMPLATES["default"])

        logger.info(f"[orchestrator] {company_name} classified as '{industry_key}' (sector={sector}, industry={industry})")

        # 4. Build safe stock data dict (convert non-serializable values)
        safe_data = {}
        for k, v in info.items():
            if v is None:
                safe_data[k] = None
            elif isinstance(v, (str, int, float, bool)):
                safe_data[k] = v
            elif isinstance(v, (list, dict)):
                safe_data[k] = v
            else:
                safe_data[k] = str(v)

        # 5. Create the SharedState
        state = SharedState(
            ticker=info.get("symbol", ticker),
            company_name=company_name,
            industry=industry,
            sector=sector,
            currency=currency,
            current_price=float(current_price) if current_price else None,
            summary=summary,
            industry_instructions=instructions,
            stock_data=safe_data,
        )
        state.agent_statuses["orchestrator"] = "completed"

        logger.info(f"[orchestrator] SharedState created for {state.ticker}")
        return state


# Singleton instance
orchestrator = OrchestratorAgent()
