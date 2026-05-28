"""
Agent 3: The Qualitative Agent (The Business Strategist)

Responsibilities:
- Competitive moat identification (brand, network effects, cost leadership)
- Management quality assessment
- Growth catalyst identification
- Business model durability analysis
- Narrative explanation connecting the "why" behind the numbers
"""

import logging
from app.agents.base_agent import BaseAgent
from app.agents.shared_state import SharedState, QualitativeOutput

logger = logging.getLogger("vittsarathi.agents.qualitative")

SYSTEM_PROMPT = """You are a senior business strategist at a premier consulting firm. Your expertise is PURELY QUALITATIVE — you think in narratives, competitive advantages, and business strategy.

Your task: Analyze the provided company data and produce a strategic business assessment.

RULES:
1. Base your analysis ONLY on the data provided. Do NOT make claims you cannot support from the data.
2. Focus on the NARRATIVE — the "why" behind the numbers.
3. Identify competitive moats using the framework: Brand Power, Network Effects, Switching Costs, Cost Leadership, Intangible Assets.
4. Assess management quality through their capital allocation and stated strategy.
5. Be specific and actionable. Don't say "good company" — explain WHY.
6. Adapt your analysis to the industry-specific focus provided.

Respond in VALID JSON with exactly these keys:
{
  "moat_analysis": "...",
  "management_quality": "...",
  "growth_catalysts": "...",
  "business_model": "...",
  "narrative_explanation": "..."
}"""


class QualitativeAgent(BaseAgent):
    """Agent 3: The Business Strategist — narrative, moat, and strategy."""

    agent_name = "qualitative"
    model = "gpt-3.5-turbo"

    def _build_prompt(self, state: SharedState) -> str:
        """Build user prompt with company context and business data."""
        data = state.stock_data
        instructions = state.industry_instructions.get("qualitative_focus", "")

        context = {
            "Company": state.company_name,
            "Ticker": state.ticker,
            "Sector": state.sector,
            "Industry": state.industry,
            "Business Summary": state.summary[:500] if state.summary else "Not available",
            "Market Cap": data.get("marketCap"),
            "Revenue": data.get("totalRevenue"),
            "Revenue Growth": data.get("revenueGrowth"),
            "Profit Margins": data.get("profitMargins"),
            "ROE": data.get("returnOnEquity"),
            "Insider Holding %": data.get("heldPercentInsiders"),
            "Institutional Holding %": data.get("heldPercentInstitutions"),
            "Recommendation": data.get("recommendationKey"),
            "Target Price": data.get("targetMeanPrice"),
            "Number of Analysts": data.get("numberOfAnalystOpinions"),
            "Full Time Employees": data.get("fullTimeEmployees"),
        }

        context_str = "\n".join(f"  {k}: {v}" for k, v in context.items() if v is not None)

        return f"""Analyze the following company:

{context_str}

INDUSTRY-SPECIFIC FOCUS:
{instructions}

Produce your qualitative business assessment as a JSON object."""

    async def execute(self, state: SharedState) -> SharedState:
        state.agent_statuses["qualitative"] = "running"
        logger.info(f"[qualitative] Analyzing {state.ticker}")

        prompt = self._build_prompt(state)
        response_text = self._call_llm(SYSTEM_PROMPT, prompt)
        parsed = self._parse_json(response_text)

        if "_parse_error" in parsed:
            state.qualitative = QualitativeOutput(
                moat_analysis="Analysis completed — see raw text",
                management_quality=parsed.get("_raw_text", "")[:200],
                growth_catalysts="JSON parse failed",
                business_model="JSON parse failed",
                narrative_explanation="JSON parse failed",
            )
        else:
            state.qualitative = QualitativeOutput(
                moat_analysis=parsed.get("moat_analysis", "N/A"),
                management_quality=parsed.get("management_quality", "N/A"),
                growth_catalysts=parsed.get("growth_catalysts", "N/A"),
                business_model=parsed.get("business_model", "N/A"),
                narrative_explanation=parsed.get("narrative_explanation", "N/A"),
            )

        state.agent_statuses["qualitative"] = "completed"
        logger.info(f"[qualitative] Done for {state.ticker}")
        return state


# Singleton instance
qualitative_agent = QualitativeAgent()
