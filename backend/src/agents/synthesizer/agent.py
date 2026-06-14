import json
import re
import logging
from src.agents.base.base_agent import BaseAgent
from src.agents.base.shared_state import SharedState, ResponseType
from .config import SynthesizerConfig

logger = logging.getLogger("vittsarathi.agents.synthesizer")


class SynthesizerAgent(BaseAgent):

    def __init__(self):
        self.config      = SynthesizerConfig
        self.agent_name  = self.config["name"]
        self.model       = self.config["model"]
        self.max_tokens  = self.config.get("max_tokens", 2500)
        self.system_prompt = self.config["system_prompt"]

    # ─────────────────────────────────────────────
    # CAVEAT BLOCK
    # Tells the LLM what data is missing so it
    # does not hallucinate failed agent output.
    # ─────────────────────────────────────────────

    def _build_caveat_block(self, state: SharedState) -> str:
        failed  = []
        partial = []

        agent_map = {
            "quantitative":    state.quantitative_result,
            "qualitative":     state.qualitative_result,
            "risk_governance": state.risk_governance_result,
            "sentiment":       state.sentiment_result,
        }

        for name, result in agent_map.items():
            if result is None:
                failed.append(name)
            elif result.status == "failed":
                failed.append(name)
            elif result.status == "partial":
                partial.append(name)

        if not failed and not partial:
            return ""

        lines = ["⚠ DATA QUALITY WARNINGS — READ BEFORE SYNTHESIZING:"]
        if failed:
            lines.append(
                f"MISSING DATA: {', '.join(failed)} produced NO output. "
                f"Do NOT speculate. Mark as 'Insufficient data'."
            )
        if partial:
            lines.append(
                f"PARTIAL DATA: {', '.join(partial)} returned incomplete output. "
                f"Tag conclusions [low confidence]."
            )
        return "\n".join(lines)

    # ─────────────────────────────────────────────
    # PROMPT BUILDERS — one per response_type
    # ─────────────────────────────────────────────

    def _build_dashboard_prompt(self, state: SharedState) -> str:
        caveat = self._build_caveat_block(state)
        sections = []

        if caveat:
            sections.append(caveat)
            sections.append("")

        sections.append(f"USER QUERY: '{state.user_query}'")
        sections.append(f"COMPANY: {state.company_name} ({state.ticker})")
        sections.append(f"SECTOR: {state.sector} | INDUSTRY: {state.industry}")
        sections.append(f"PRICE: {state.currency} {state.current_price}")
        sections.append("")

        if state.quantitative:
            q = state.quantitative
            sections.append("═══ QUANTITATIVE ANALYSIS ═══")
            sections.append(f"Framework: {q.industry_framework_used}")
            for block_name, block_text in q.analysis_blocks.items():
                sections.append(f"{block_name}: {block_text}")
            sections.append(f"Overall Health: {q.overall_quantitative_health}")
            if q.raw_ratios:
                sections.append(f"Raw Ratios: {q.raw_ratios}")
            sections.append("")
        else:
            sections.append("═══ QUANTITATIVE ANALYSIS: UNAVAILABLE ═══\n")

        if state.qualitative:
            ql = state.qualitative
            sections.append("═══ QUALITATIVE ASSESSMENT ═══")
            sections.append(f"Moat: {ql.moat_analysis}")
            sections.append(f"Management: {ql.management_quality}")
            sections.append(f"Growth Catalysts: {ql.growth_catalysts}")
            sections.append(f"Business Model: {ql.business_model}")
            sections.append(f"Narrative: {ql.narrative_explanation}")
            sections.append("")
        else:
            sections.append("═══ QUALITATIVE ASSESSMENT: UNAVAILABLE ═══\n")

        if state.risk_governance:
            r = state.risk_governance
            sections.append("═══ RISK & GOVERNANCE ═══")
            sections.append(f"Framework: {r.industry_framework_used}")
            for block_name, block_text in r.analysis_blocks.items():
                sections.append(f"{block_name}: {block_text}")
            sections.append(f"Overall Governance: {r.overall_governance_health}")
            if r.raw_metrics:
                sections.append(f"Raw Metrics: {r.raw_metrics}")
            sections.append("")
        else:
            sections.append("═══ RISK & GOVERNANCE: UNAVAILABLE ═══\n")

        if state.sentiment:
            s = state.sentiment
            sections.append("═══ SENTIMENT & MACRO ═══")
            sections.append(f"Overall Mood: {s.market_sentiment.overall_mood}")
            sections.append(f"Themes: {', '.join(s.market_sentiment.dominant_news_themes)}")
            sections.append(f"Tailwinds: {', '.join(s.sector_factors.tailwinds)}")
            sections.append(f"Headwinds: {', '.join(s.sector_factors.headwinds)}")
            for macro_name, macro_data in s.macroeconomic_environment.metrics.items():
                sections.append(
                    f"Macro — {macro_name}: "
                    f"{macro_data.get('current_value')} "
                    f"(trend: {macro_data.get('trend')}) — "
                    f"{macro_data.get('business_impact')}"
                )
            sections.append("")
        else:
            sections.append("═══ SENTIMENT & MACRO: UNAVAILABLE ═══\n")

        sections.append("═══ YOUR TASK ═══")
        sections.append(
            "Synthesize the above into a cohesive investment thesis. "
            "Resolve contradictions. Populate ALL fields of SynthesizerOutput. "
            "Set targeted_answer to null. "
            "Return a single JSON object and nothing else."
        )
        return "\n".join(sections)

    def _build_chat_prompt(self, state: SharedState) -> str:
        caveat = self._build_caveat_block(state)
        sections = []

        sections.append("YOU ARE IN CHAT MODE.")
        sections.append(
            "Answer ONLY the user's follow-up question. "
            "Be concise. Do not rebuild the full thesis."
        )
        sections.append("")

        if caveat:
            sections.append(caveat)
            sections.append("")

        sections.append(f"FOLLOW-UP QUESTION: '{state.user_query}'")
        sections.append(f"COMPANY: {state.company_name} ({state.ticker})")
        sections.append("")
        sections.append("EXISTING ANALYSIS CONTEXT:")

        if state.quantitative:
            q = state.quantitative
            sections.append(f"Quantitative — {q.overall_quantitative_health}")
            for block_name, block_text in q.analysis_blocks.items():
                sections.append(f"  {block_name}: {block_text}")

        if state.qualitative:
            ql = state.qualitative
            sections.append(f"Qualitative — Moat: {ql.moat_analysis}")
            sections.append(f"  Growth: {ql.growth_catalysts}")

        if state.risk_governance:
            r = state.risk_governance
            sections.append(f"Risk — {r.overall_governance_health}")

        if state.sentiment:
            s = state.sentiment
            sections.append(f"Sentiment — {s.market_sentiment.overall_mood}")

        sections.append("")
        sections.append("═══ YOUR TASK ═══")
        sections.append(
            "Populate ONLY these fields in SynthesizerOutput: "
            "targeted_answer (2-4 sentences answering the question directly), "
            "executive_summary (one sentence). "
            "Set investment_decision, dynamic_investment_pillars, "
            "key_risk_dashboard all to null. "
            "Return a single JSON object and nothing else."
        )
        return "\n".join(sections)

    def _build_patch_prompt(self, state: SharedState) -> str:
        sections = []

        sections.append("YOU ARE IN PATCH MODE.")
        sections.append(
            "The user wants to update a specific part of the dashboard. "
            "Only return the fields that need to change."
        )
        sections.append("")
        sections.append(f"UPDATE REQUEST: '{state.user_query}'")
        sections.append(f"COMPANY: {state.company_name} ({state.ticker})")
        sections.append("")

        if state.quantitative:
            q = state.quantitative
            sections.append("CURRENT QUANTITATIVE STATE:")
            for block_name, block_text in q.analysis_blocks.items():
                sections.append(f"  {block_name}: {block_text}")
            sections.append("")

        if state.risk_governance:
            r = state.risk_governance
            sections.append("CURRENT RISK STATE:")
            sections.append(f"  {r.overall_governance_health}")
            sections.append("")

        sections.append("═══ YOUR TASK ═══")
        sections.append(
            "Produce a SynthesizerOutput JSON. "
            "Set targeted_answer to a one-sentence confirmation of what changed. "
            "Set key_risk_dashboard with ONLY changed risk entries. "
            "Set dynamic_investment_pillars with ONLY changed pillars. "
            "Set investment_decision to null unless explicitly re-rated. "
            "Return a single JSON object and nothing else."
        )
        return "\n".join(sections)

    def _build_prompt(self, state: SharedState) -> str:
        response_type = (
            state.execution_plan.response_type
            if state.execution_plan
            else ResponseType.DASHBOARD
        )
        if response_type == ResponseType.CHAT:
            return self._build_chat_prompt(state)
        elif response_type == ResponseType.PATCH:
            return self._build_patch_prompt(state)
        else:
            return self._build_dashboard_prompt(state)

    # ─────────────────────────────────────────────
    # EXECUTE
    # ─────────────────────────────────────────────

    async def execute(self, state: SharedState) -> SharedState:
        from src.agents.base.shared_state import SynthesizerOutput

        state.agent_statuses[self.agent_name] = "running"
        logger.info(
            f"[{self.agent_name}] Starting for {state.ticker} — "
            f"mode: {state.execution_plan.response_type if state.execution_plan else 'dashboard'}"
        )

        prompt = self._build_prompt(state)

        llm = self._get_llm()
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user",   "content": prompt},
        ]

        try:
            response = await llm.ainvoke(messages)
            response_text = response.content
        except Exception as e:
            logger.error(f"[{self.agent_name}] LLM call failed: {e}")
            state.final_thesis = "Synthesis failed — LLM call error."
            state.investment_verdict = "Neutral"
            state.confidence_level = "Low"
            state.agent_statuses[self.agent_name] = "failed"
            return state

        try:
            clean = re.sub(r"```json|```", "", response_text).strip()
            parsed = json.loads(clean)
        except json.JSONDecodeError as e:
            logger.error(f"[{self.agent_name}] JSON parse failed: {e}")
            logger.debug(f"[{self.agent_name}] Raw response: {response_text[:500]}")
            state.final_thesis = response_text
            state.investment_verdict = "Neutral"
            state.confidence_level = "Low"
            state.agent_statuses[self.agent_name] = "failed"
            return state

        try:
            synth_out = SynthesizerOutput(**parsed)
        except Exception as e:
            logger.error(f"[{self.agent_name}] SynthesizerOutput validation failed: {e}")
            state.final_thesis = "Synthesis failed — output validation error."
            state.investment_verdict = "Neutral"
            state.confidence_level = "Low"
            state.agent_statuses[self.agent_name] = "failed"
            return state

        state.synthesis = synth_out

        if synth_out.investment_decision:
            state.investment_verdict = synth_out.investment_decision.final_rating
            state.confidence_level   = str(synth_out.investment_decision.conviction_score)
        else:
            state.investment_verdict = "Targeted Response"
            state.confidence_level   = "N/A"

        response_type = (
            state.execution_plan.response_type
            if state.execution_plan
            else ResponseType.DASHBOARD
        )

        if response_type == ResponseType.CHAT:
            md = f"## Answer\n{synth_out.targeted_answer or synth_out.executive_summary}\n"

        elif response_type == ResponseType.PATCH:
            md = f"## Update Applied\n{synth_out.targeted_answer or 'Dashboard updated.'}\n"
            if synth_out.key_risk_dashboard:
                md += "\n## Updated Risk Dashboard\n"
                for r_name, r_val in synth_out.key_risk_dashboard.items():
                    md += f"- **{r_name}**: {r_val}\n"

        else:
            md = f"## Executive Summary\n{synth_out.executive_summary}\n\n"
            if synth_out.conflict_resolution_log:
                md += "## Conflict Resolution\n"
                for c in synth_out.conflict_resolution_log:
                    md += f"- **{c.conflict_identified}** (Severity: {c.severity})\n"
                    md += f"  - {c.synthesized_resolution}\n\n"
            if synth_out.dynamic_investment_pillars:
                md += "## Investment Pillars\n"
                for p_name, p_data in synth_out.dynamic_investment_pillars.items():
                    md += f"### {p_name.replace('_', ' ').title()}\n"
                    md += f"{p_data.thesis}\n"
                    for m in p_data.supporting_metrics:
                        md += f"- {m.metric}: {m.value} ({m.status})\n"
                    md += "\n"
            if synth_out.key_risk_dashboard:
                md += "## Risk Dashboard\n"
                for r_name, r_val in synth_out.key_risk_dashboard.items():
                    md += f"- **{r_name}**: {r_val}\n"

        state.final_thesis = md
        state.agent_statuses[self.agent_name] = "completed"
        logger.info(
            f"[{self.agent_name}] Done — "
            f"verdict: {state.investment_verdict} "
            f"confidence: {state.confidence_level}"
        )
        return state


synthesizer = SynthesizerAgent()
