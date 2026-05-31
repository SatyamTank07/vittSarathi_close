import logging
from src.agents.base.base_agent import BaseAgent
from src.agents.base.shared_state import SharedState
from .config import SynthesizerConfig

logger = logging.getLogger("vittsarathi.agents.synthesizer")

class SynthesizerAgent(BaseAgent):
    def __init__(self):
        self.config = SynthesizerConfig
        self.agent_name = self.config["name"]
        self.model = self.config["model"]
        self.max_tokens = self.config.get("max_tokens", 700)
        self.system_prompt = self.config["system_prompt"]

    def _build_prompt(self, state: SharedState) -> str:
        sections = []

        sections.append(f"USER QUERY: '{state.user_query}'")
        sections.append(f"COMPANY: {state.company_name} ({state.ticker})")
        sections.append(f"SECTOR: {state.sector} | INDUSTRY: {state.industry}")
        sections.append(f"PRICE: {state.currency} {state.current_price}")
        sections.append("")

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

        if state.qualitative:
            ql = state.qualitative
            sections.append("═══ QUALITATIVE ASSESSMENT (Agent 3 — The Strategist) ═══")
            sections.append(f"Competitive Moat: {ql.moat_analysis}")
            sections.append(f"Management: {ql.management_quality}")
            sections.append(f"Growth Catalysts: {ql.growth_catalysts}")
            sections.append(f"Business Model: {ql.business_model}")
            sections.append(f"Narrative: {ql.narrative_explanation}")
            sections.append("")

        if state.risk_governance:
            r = state.risk_governance
            sections.append("═══ RISK INVESTIGATION (Agent 4 — The Investigator) ═══")
            sections.append(f"Red Flags: {', '.join(r.red_flags) if r.red_flags else 'None identified'}")
            sections.append(f"Governance Score: {r.governance_score}")
            sections.append(f"Structural Risks: {r.structural_risks}")
            sections.append(f"Insider Activity: {r.insider_activity}")
            sections.append(f"Overall Risk Level: {r.overall_risk_level}")
            sections.append("")

        if state.sentiment:
            s = state.sentiment
            sections.append("═══ SENTIMENT & MACRO (Agent 5) ═══")
            sections.append(f"Overall Mood: {s.market_sentiment.overall_mood}")
            sections.append(f"Themes: {', '.join(s.market_sentiment.dominant_news_themes)}")
            sections.append(f"Sector Tailwinds: {', '.join(s.sector_factors.tailwinds)}")
            sections.append(f"Sector Headwinds: {', '.join(s.sector_factors.headwinds)}")
            sections.append("")

        sections.append("═══ YOUR TASK ═══")
        sections.append("Synthesize the above reports into a cohesive investment thesis.")
        sections.append("Resolve any contradictions between the reports.")
        sections.append("Produce your final assessment as a JSON object.")

        return "\n".join(sections)

    async def execute(self, state: SharedState) -> SharedState:
        state.agent_statuses[self.agent_name] = "running"
        logger.info(f"[{self.agent_name}] Compiling final thesis for {state.ticker}")

        prompt = self._build_prompt(state)
        response_text = self._call_llm(self.system_prompt, prompt)
        parsed = self._parse_json(response_text)

        if "_parse_error" in parsed:
            state.final_thesis = parsed.get("_raw_text", "Synthesis failed — raw output unavailable.")
            state.investment_verdict = "Neutral"
            state.confidence_level = "Low"
        else:
            from src.agents.base.shared_state import SynthesizerOutput
            try:
                synth_out = SynthesizerOutput(**parsed)
                state.synthesis = synth_out
                
                if synth_out.investment_decision:
                    state.investment_verdict = synth_out.investment_decision.final_rating
                    state.confidence_level = str(synth_out.investment_decision.conviction_score)
                else:
                    state.investment_verdict = "Targeted Response"
                    state.confidence_level = "N/A"
                
                # Format to markdown for frontend and db
                if synth_out.targeted_answer:
                    md = f"## Targeted Answer\n{synth_out.targeted_answer}\n\n"
                    md += f"**Summary**: {synth_out.executive_summary}\n\n"
                else:
                    md = f"## Executive Summary\n{synth_out.executive_summary}\n\n"
                
                if synth_out.conflict_resolution_log:
                    md += "## Conflict Resolution\n"
                    for c in synth_out.conflict_resolution_log:
                        md += f"- **Conflict Identified**: {c.conflict_identified}\n"
                        md += f"  - *Severity*: {c.severity}\n"
                        md += f"  - *Resolution*: {c.synthesized_resolution}\n\n"
                        
                if synth_out.dynamic_investment_pillars:
                    md += "## Dynamic Investment Pillars\n"
                    for p_name, p_data in synth_out.dynamic_investment_pillars.items():
                        title = p_name.replace('_', ' ').title()
                        md += f"### {title}\n"
                        md += f"**Thesis**: {p_data.thesis}\n\n"
                        if p_data.supporting_metrics:
                            md += "**Supporting Metrics**:\n"
                            for m in p_data.supporting_metrics:
                                md += f"- {m.metric}: {m.value} ({m.status})\n"
                        md += "\n"
                        
                if synth_out.key_risk_dashboard:
                    md += "## Key Risk Dashboard\n"
                    for r_name, r_val in synth_out.key_risk_dashboard.items():
                        title = r_name.replace('_', ' ').title()
                        md += f"- **{title}**: {r_val}\n"
                        
                state.final_thesis = md
                
            except Exception as e:
                logger.error(f"Failed to parse SynthesizerOutput: {e}")
                state.final_thesis = "Synthesis succeeded but failed to parse structured output."
                state.investment_verdict = parsed.get("investment_decision", {}).get("final_rating", "Neutral")
                state.confidence_level = str(parsed.get("investment_decision", {}).get("conviction_score", "Low"))

        state.agent_statuses[self.agent_name] = "completed"
        logger.info(f"[{self.agent_name}] Verdict for {state.ticker}: {state.investment_verdict} ({state.confidence_level})")
        return state

synthesizer = SynthesizerAgent()
