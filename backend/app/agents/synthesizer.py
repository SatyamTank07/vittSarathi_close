"""
Agent 6: The Synthesizer (The Chief Investment Officer)

Responsibilities:
- Reads the completed SharedState with all agent outputs
- Cross-references and resolves contradictions
- Compiles a cohesive Markdown investment thesis
- Determines investment verdict (Bullish/Neutral/Bearish) with confidence level
"""

import logging
from app.agents.base_agent import BaseAgent
from app.agents.shared_state import SharedState

logger = logging.getLogger("vittsarathi.agents.synthesizer")

SYSTEM_PROMPT = """You are the Chief Investment Officer at a premier investment firm. You are writing the FINAL investment thesis by synthesizing three independent research reports: Quantitative Analysis, Qualitative Assessment, and Risk Investigation.

Your task: Cross-reference the reports, resolve any contradictions, and produce a clear investment verdict.

RULES:
1. If the numbers look great but the risk report raises serious concerns, DO NOT ignore the risks. Weigh them explicitly.
2. If agents contradict each other, acknowledge both views and explain your resolution.
3. Your output must be a PROFESSIONAL investment thesis in Markdown format.
4. End with a clear verdict: Bullish, Neutral, or Bearish — with a confidence level (High, Medium, Low).
5. Be balanced and evidence-based. Never recommend without citing specific data points from the agents' reports.
6. Use the specific numbers and facts from the analysis — don't generalize.

Respond in VALID JSON with exactly these keys:
{
  "final_thesis": "... full markdown report ...",
  "investment_verdict": "Bullish|Neutral|Bearish",
  "confidence_level": "High|Medium|Low"
}"""


class SynthesizerAgent(BaseAgent):
    """Agent 6: The Chief Investment Officer — synthesis, conflict resolution, final report."""

    agent_name = "synthesizer"
    model = "gpt-4o-mini"

    def _build_prompt(self, state: SharedState) -> str:
        """Build the synthesis prompt with all agent outputs."""
        sections = []

        sections.append(f"COMPANY: {state.company_name} ({state.ticker})")
        sections.append(f"SECTOR: {state.sector} | INDUSTRY: {state.industry}")
        sections.append(f"PRICE: {state.currency} {state.current_price}")
        sections.append("")

        # Quantitative report
        if state.quantitative:
            q = state.quantitative
            sections.append("═══ QUANTITATIVE ANALYSIS (Agent 2 — The Accountant) ═══")
            sections.append(f"Revenue Trend: {q.revenue_trend}")
            sections.append(f"Profit Margins: {q.profit_margin_analysis}")
            sections.append(f"Valuation: {q.valuation_assessment}")
            sections.append(f"Financial Health: {q.health_metrics}")
            sections.append(f"Sector-Specific: {q.sector_specific}")
            if q.raw_ratios:
                sections.append(f"Raw Ratios: {q.raw_ratios}")
            sections.append("")

        # Qualitative report
        if state.qualitative:
            ql = state.qualitative
            sections.append("═══ QUALITATIVE ASSESSMENT (Agent 3 — The Strategist) ═══")
            sections.append(f"Competitive Moat: {ql.moat_analysis}")
            sections.append(f"Management: {ql.management_quality}")
            sections.append(f"Growth Catalysts: {ql.growth_catalysts}")
            sections.append(f"Business Model: {ql.business_model}")
            sections.append(f"Narrative: {ql.narrative_explanation}")
            sections.append("")

        # Risk report
        if state.risk_governance:
            r = state.risk_governance
            sections.append("═══ RISK INVESTIGATION (Agent 4 — The Investigator) ═══")
            sections.append(f"Red Flags: {', '.join(r.red_flags) if r.red_flags else 'None identified'}")
            sections.append(f"Governance Score: {r.governance_score}")
            sections.append(f"Structural Risks: {r.structural_risks}")
            sections.append(f"Insider Activity: {r.insider_activity}")
            sections.append(f"Overall Risk Level: {r.overall_risk_level}")
            sections.append("")

        sections.append("═══ YOUR TASK ═══")
        sections.append("Synthesize the above three reports into a cohesive investment thesis.")
        sections.append("Resolve any contradictions between the reports.")
        sections.append("Produce your final assessment as a JSON object.")

        return "\n".join(sections)

    async def execute(self, state: SharedState) -> SharedState:
        state.agent_statuses["synthesizer"] = "running"
        logger.info(f"[synthesizer] Compiling final thesis for {state.ticker}")

        prompt = self._build_prompt(state)
        response_text = self._call_llm(SYSTEM_PROMPT, prompt)
        parsed = self._parse_json(response_text)

        if "_parse_error" in parsed:
            # If JSON parsing fails, use the raw text as the thesis
            state.final_thesis = parsed.get("_raw_text", "Synthesis failed — raw output unavailable.")
            state.investment_verdict = "Neutral"
            state.confidence_level = "Low"
        else:
            state.final_thesis = parsed.get("final_thesis", "No thesis generated.")
            state.investment_verdict = parsed.get("investment_verdict", "Neutral")
            state.confidence_level = parsed.get("confidence_level", "Low")

        state.agent_statuses["synthesizer"] = "completed"
        logger.info(f"[synthesizer] Verdict for {state.ticker}: {state.investment_verdict} ({state.confidence_level})")
        return state


# Singleton instance
synthesizer = SynthesizerAgent()
