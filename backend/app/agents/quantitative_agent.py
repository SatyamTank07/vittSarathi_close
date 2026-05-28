"""
Agent 2: The Quantitative Agent (The Accountant)

Responsibilities:
- Deterministic financial math and ratio analysis
- Historical trend identification (revenue, margins, profitability)
- Sector-adapted metric evaluation
- Valuation assessment (PE, PB, intrinsic value indicators)
- Financial health scoring (leverage, ROE, ROCE)
"""

import json
import logging
from app.agents.base_agent import BaseAgent
from app.agents.shared_state import SharedState, QuantitativeOutput

logger = logging.getLogger("vittsarathi.agents.quantitative")

SYSTEM_PROMPT = """You are a senior financial analyst working at a top investment firm. Your expertise is PURELY QUANTITATIVE — you think entirely in numbers, ratios, and mathematical trends.

Your task: Analyze the provided stock data and produce a structured financial assessment.

RULES:
1. Base your analysis ONLY on the data provided. Do NOT hallucinate numbers.
2. If a metric is missing or null, say "Data not available" — never invent values.
3. Be specific with numbers. Don't say "good margins" — say "profit margin of 18.5% which is above the industry average."
4. Adapt your analysis to the industry-specific focus provided.
5. Be concise but substantive. Every sentence should contain a fact or insight.

Respond in VALID JSON with exactly these keys:
{
  "revenue_trend": "...",
  "profit_margin_analysis": "...",
  "valuation_assessment": "...",
  "health_metrics": "...",
  "sector_specific": "...",
  "raw_ratios": { ... computed numeric values ... }
}"""


class QuantitativeAgent(BaseAgent):
    """Agent 2: The Accountant — pure numbers and ratios."""

    agent_name = "quantitative"
    model = "gpt-3.5-turbo"

    def _build_prompt(self, state: SharedState) -> str:
        """Build the user prompt with all relevant financial data."""
        data = state.stock_data
        instructions = state.industry_instructions.get("quantitative_focus", "")

        # Extract key financial metrics for the prompt
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
        state.agent_statuses["quantitative"] = "running"
        logger.info(f"[quantitative] Analyzing {state.ticker}")

        prompt = self._build_prompt(state)
        response_text = self._call_llm(SYSTEM_PROMPT, prompt)
        parsed = self._parse_json(response_text)

        # Handle parse failures gracefully
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

        state.agent_statuses["quantitative"] = "completed"
        logger.info(f"[quantitative] Done for {state.ticker}")
        return state


# Singleton instance
quantitative_agent = QuantitativeAgent()
