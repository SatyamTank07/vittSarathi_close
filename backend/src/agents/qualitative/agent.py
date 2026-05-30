import logging
from src.agents.base.base_agent import BaseAgent
from src.agents.base.shared_state import SharedState, QualitativeOutput
from .config import QualitativeConfig

logger = logging.getLogger("vittsarathi.agents.qualitative")

class QualitativeAgent(BaseAgent):
    def __init__(self):
        self.config = QualitativeConfig
        self.agent_name = self.config["name"]
        self.model = self.config["model"]
        self.max_tokens = self.config.get("max_tokens", 700)
        self.system_prompt = self.config["system_prompt"]

    def _build_prompt(self, state: SharedState) -> str:
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
        state.agent_statuses[self.agent_name] = "running"
        logger.info(f"[{self.agent_name}] Analyzing {state.ticker}")

        prompt = self._build_prompt(state)
        response_text = self._call_llm(self.system_prompt, prompt)
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

        state.agent_statuses[self.agent_name] = "completed"
        logger.info(f"[{self.agent_name}] Done for {state.ticker}")
        return state

qualitative_agent = QualitativeAgent()
