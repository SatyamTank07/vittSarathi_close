import logging
from src.agents.base.base_agent import BaseAgent
from src.agents.base.shared_state import SharedState, RiskGovernanceOutput
from .config import RiskGovernanceConfig

logger = logging.getLogger("vittsarathi.agents.risk")

class RiskGovernanceAgent(BaseAgent):
    def __init__(self):
        self.config = RiskGovernanceConfig
        self.agent_name = self.config["name"]
        self.model = self.config["model"]
        self.max_tokens = self.config.get("max_tokens", 700)
        self.system_prompt = self.config["system_prompt"]

    def _build_prompt(self, state: SharedState) -> str:
        data = state.stock_data
        instructions = state.industry_instructions.get("risk_focus", "")

        risk_data = {
            "Company": state.company_name,
            "Ticker": state.ticker,
            "Sector": state.sector,
            "Industry": state.industry,
            "Current Price": state.current_price,
            "Market Cap": data.get("marketCap"),
            "PE Ratio (Trailing)": data.get("trailingPE"),
            "PE Ratio (Forward)": data.get("forwardPE"),
            "PB Ratio": data.get("priceToBook"),
            "Debt to Equity": data.get("debtToEquity"),
            "Current Ratio": data.get("currentRatio"),
            "Quick Ratio": data.get("quickRatio"),
            "Total Debt": data.get("totalDebt"),
            "Total Cash": data.get("totalCash"),
            "Free Cash Flow": data.get("freeCashflow"),
            "Insider Holding %": data.get("heldPercentInsiders"),
            "Institutional Holding %": data.get("heldPercentInstitutions"),
            "Beta": data.get("beta"),
            "52W High": data.get("fiftyTwoWeekHigh"),
            "52W Low": data.get("fiftyTwoWeekLow"),
            "Audit Risk": data.get("auditRisk"),
            "Board Risk": data.get("boardRisk"),
            "Compensation Risk": data.get("compensationRisk"),
            "Shareholder Rights Risk": data.get("shareHolderRightsRisk"),
            "Overall Risk": data.get("overallRisk"),
            "Recommendation": data.get("recommendationKey"),
            "Short Ratio": data.get("shortRatio"),
            "Short % of Float": data.get("shortPercentOfFloat"),
            "Payout Ratio": data.get("payoutRatio"),
        }

        risk_str = "\n".join(f"  {k}: {v}" for k, v in risk_data.items() if v is not None)

        return f"""Investigate the following company for risks and governance concerns:

{risk_str}

INDUSTRY-SPECIFIC RISK FOCUS:
{instructions}

Produce your risk assessment as a JSON object. Be thorough and skeptical."""

    async def execute(self, state: SharedState) -> SharedState:
        state.agent_statuses[self.agent_name] = "running"
        logger.info(f"[{self.agent_name}] Investigating {state.ticker}")

        prompt = self._build_prompt(state)
        response_text = self._call_llm(self.system_prompt, prompt)
        parsed = self._parse_json(response_text)

        if "_parse_error" in parsed:
            state.risk_governance = RiskGovernanceOutput(
                red_flags=["Analysis produced unstructured output — manual review needed"],
                governance_score="moderate",
                structural_risks=parsed.get("_raw_text", "")[:200],
                insider_activity="JSON parse failed",
                overall_risk_level="medium",
            )
        else:
            red_flags = parsed.get("red_flags", [])
            if isinstance(red_flags, str):
                red_flags = [red_flags]

            state.risk_governance = RiskGovernanceOutput(
                red_flags=red_flags,
                governance_score=parsed.get("governance_score", "moderate"),
                structural_risks=parsed.get("structural_risks", "N/A"),
                insider_activity=parsed.get("insider_activity", "N/A"),
                overall_risk_level=parsed.get("overall_risk_level", "medium"),
            )

        state.agent_statuses[self.agent_name] = "completed"
        logger.info(f"[{self.agent_name}] Done for {state.ticker}")
        return state

risk_agent = RiskGovernanceAgent()
