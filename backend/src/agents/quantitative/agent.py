import logging
from src.agents.base.base_agent import BaseAgent
from src.agents.base.shared_state import SharedState, QuantitativeOutput
from .config import QuantitativeConfig

logger = logging.getLogger("vittsarathi.agents.quantitative")

class QuantitativeAgent(BaseAgent):
    def __init__(self):
        self.config = QuantitativeConfig
        self.agent_name = self.config["name"]
        self.model = self.config["model"]
        self.max_tokens = self.config.get("max_tokens", 700)
        self.system_prompt = self.config["system_prompt"]

    def _build_prompt(self, state: SharedState) -> str:
        data = state.stock_data
        instructions = state.industry_instructions.get("quantitative_focus", "")

        metrics = {
            "Company": state.company_name,
            "Ticker": state.ticker,
            "Sector": state.sector,
            "Industry": state.industry,
            "Currency": state.currency,
            "Current Price": state.current_price,
            "Market Cap": data.get("marketCap"),
            "PE Ratio (Trailing)": data.get("trailingPE"),
            "PE Ratio (Forward)": data.get("forwardPE"),
            "PB Ratio": data.get("priceToBook"),
            "PEG Ratio": data.get("pegRatio"),
            "EV/EBITDA": data.get("enterpriseToEbitda"),
            "Revenue": data.get("totalRevenue"),
            "Revenue Growth": data.get("revenueGrowth"),
            "Earnings Growth": data.get("earningsGrowth"),
            "Gross Margins": data.get("grossMargins"),
            "EBITDA Margins": data.get("ebitdaMargins"),
            "Profit Margins": data.get("profitMargins"),
            "Operating Margins": data.get("operatingMargins"),
            "ROE": data.get("returnOnEquity"),
            "ROA": data.get("returnOnAssets"),
            "Debt to Equity": data.get("debtToEquity"),
            "Current Ratio": data.get("currentRatio"),
            "Quick Ratio": data.get("quickRatio"),
            "Total Debt": data.get("totalDebt"),
            "Total Cash": data.get("totalCash"),
            "Free Cash Flow": data.get("freeCashflow"),
            "Operating Cash Flow": data.get("operatingCashflow"),
            "Dividend Yield": data.get("dividendYield"),
            "Payout Ratio": data.get("payoutRatio"),
            "52W High": data.get("fiftyTwoWeekHigh"),
            "52W Low": data.get("fiftyTwoWeekLow"),
            "50D Average": data.get("fiftyDayAverage"),
            "200D Average": data.get("twoHundredDayAverage"),
            "Beta": data.get("beta"),
        }

        metrics_str = "\n".join(f"  {k}: {v}" for k, v in metrics.items() if v is not None)

        return f"""Analyze the following stock data:

{metrics_str}

INDUSTRY-SPECIFIC FOCUS:
{instructions}

Produce your quantitative analysis as a JSON object."""

    async def execute(self, state: SharedState) -> SharedState:
        state.agent_statuses[self.agent_name] = "running"
        logger.info(f"[{self.agent_name}] Analyzing {state.ticker}")

        prompt = self._build_prompt(state)
        response_text = self._call_llm(self.system_prompt, prompt)
        parsed = self._parse_json(response_text)

        if "_parse_error" in parsed:
            state.quantitative = QuantitativeOutput(
                revenue_trend="Analysis completed — see raw text",
                profit_margin_analysis=parsed.get("_raw_text", "")[:200],
                valuation_assessment="JSON parse failed",
                health_metrics="JSON parse failed",
                sector_specific="JSON parse failed",
                raw_ratios={},
            )
        else:
            state.quantitative = QuantitativeOutput(
                revenue_trend=parsed.get("revenue_trend", "N/A"),
                profit_margin_analysis=parsed.get("profit_margin_analysis", "N/A"),
                valuation_assessment=parsed.get("valuation_assessment", "N/A"),
                health_metrics=parsed.get("health_metrics", "N/A"),
                sector_specific=parsed.get("sector_specific", "N/A"),
                raw_ratios=parsed.get("raw_ratios", {}),
            )

        state.agent_statuses[self.agent_name] = "completed"
        logger.info(f"[{self.agent_name}] Done for {state.ticker}")
        return state

quantitative_agent = QuantitativeAgent()
