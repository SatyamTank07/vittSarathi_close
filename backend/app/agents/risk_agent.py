"""
Agent 4: The Risk & Governance Agent (The Internal Investigator)

Responsibilities:
- Purely DEFENSIVE analysis — assumes hidden dangers exist
- Management integrity checks (insider selling, auditor changes)
- Structural vulnerability assessment (share pledging, debt traps)
- Corporate governance red flag detection
- The "Lie Detector" — finds reasons NOT to invest
"""

import logging
from app.agents.base_agent import BaseAgent
from app.agents.shared_state import SharedState, RiskGovernanceOutput

logger = logging.getLogger("vittsarathi.agents.risk")

SYSTEM_PROMPT = """You are a forensic financial investigator and corporate governance specialist. Your job is to be SKEPTICAL and DEFENSIVE. You are the "lie detector" of the analysis team.

Your task: Find every possible risk, red flag, and governance concern about this company.

RULES:
1. ASSUME there might be hidden dangers. Your job is to PROTECT the investor.
2. Base your analysis ONLY on the data provided. If data for a risk check is missing, flag it as "CANNOT VERIFY — data not available" which is itself a mild red flag.
3. Never give a company a pass just because the stock price is rising.
4. Focus on: insider selling patterns, high promoter pledge, auditor changes, related-party transactions, extreme valuations, and structural debt risks.
5. If insider holdings are very low or decreasing, flag it as a concern.
6. If debt-to-equity is high relative to the sector, flag it.
7. Be blunt and direct. Investors need warnings, not sugar-coating.

Respond in VALID JSON with exactly these keys:
{
  "red_flags": ["flag1", "flag2", ...],
  "governance_score": "strong|moderate|weak",
  "structural_risks": "...",
  "insider_activity": "...",
  "overall_risk_level": "low|medium|high"
}"""


class RiskGovernanceAgent(BaseAgent):
    """Agent 4: The Internal Investigator — skeptical, defensive analysis."""

    agent_name = "risk_governance"
    model = "gpt-3.5-turbo"

    def _build_prompt(self, state: SharedState) -> str:
        """Build user prompt with risk-relevant data points."""
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
        state.agent_statuses["risk_governance"] = "running"
        logger.info(f"[risk_governance] Investigating {state.ticker}")

        prompt = self._build_prompt(state)
        response_text = self._call_llm(SYSTEM_PROMPT, prompt)
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

        state.agent_statuses["risk_governance"] = "completed"
        logger.info(f"[risk_governance] Done for {state.ticker}")
        return state


# Singleton instance
risk_agent = RiskGovernanceAgent()
