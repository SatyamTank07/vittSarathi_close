import logging
import yfinance as yf
from src.agents.base.base_agent import BaseAgent
from src.agents.base.shared_state import SharedState
from .config import OrchestratorConfig

logger = logging.getLogger("vittsarathi.agents.orchestrator")

def _classify_industry(sector: str, industry: str) -> str:
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
    ticker_clean = ticker.upper().strip()

    ticker_obj = yf.Ticker(ticker_clean)
    info = {}
    try:
        info = ticker_obj.info
    except Exception:
        info = {}

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
    def __init__(self):
        self.config = OrchestratorConfig
        self.agent_name = self.config["name"]
        self.model = self.config["model"]
        self.max_tokens = self.config.get("max_tokens", 700)
        self.industry_templates = self.config["industry_templates"]

    async def execute(self, state: SharedState = None, ticker: str = None) -> SharedState:
        if not ticker:
            raise ValueError("Orchestrator requires a ticker symbol.")

        logger.info(f"[{self.agent_name}] Starting analysis for {ticker}")

        info = _fetch_stock_data(ticker)

        company_name = info.get("longName", info.get("shortName", ticker))
        sector = info.get("sector", "Unknown")
        industry = info.get("industry", "Unknown")
        currency = info.get("currency", "USD")
        current_price = info.get("currentPrice", info.get("regularMarketPrice"))
        summary = info.get("longBusinessSummary", "")

        industry_key = _classify_industry(sector, industry)
        instructions = self.industry_templates.get(industry_key, self.industry_templates["default"])

        logger.info(f"[{self.agent_name}] {company_name} classified as '{industry_key}' (sector={sector}, industry={industry})")

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
        state.agent_statuses[self.agent_name] = "completed"

        logger.info(f"[{self.agent_name}] SharedState created for {state.ticker}")
        return state

orchestrator = OrchestratorAgent()
