import json
import re
import logging
from typing import Dict, Any, List
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
            
        # Check macro data freshness
        if state.sentiment and state.sentiment.macroeconomic_environment:
            macro_env = state.sentiment.macroeconomic_environment
            if macro_env.fetched_at:
                from datetime import datetime, timezone
                try:
                    fetched = datetime.fromisoformat(macro_env.fetched_at)
                    age_hours = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600
                    if age_hours > 24:
                        lines.append(
                            f"MACRO DATA NOTE: Macroeconomic data was fetched "
                            f"{int(age_hours)} hours ago (as of {macro_env.fetched_at[:10]}). "
                            f"Caveat any macro-dependent conclusions with the fetched date."
                        )
                except ValueError:
                    pass  # unparseable timestamp, skip caveat
            
            # Check individual metric staleness (World Bank GDP is always annual)
            for metric_name, metric_data in macro_env.metrics.items():
                if isinstance(metric_data, dict) and metric_data.get("source") == "World Bank":
                    period = metric_data.get("period", "unknown period")
                    lines.append(
                        f"MACRO NOTE: '{metric_name}' is from World Bank "
                        f"(annual data, period: {period}). Do not present as current."
                    )
                    
        if len(lines) == 1:
            return ""

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
            "The user wants to update a specific part of the existing dashboard. "
            "Return ONLY the fields that need to change. "
            "Do not rebuild the full analysis."
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

            if q.raw_ratios:
                sections.append(f"  Raw Ratios: {q.raw_ratios}")
            sections.append("")

        if state.risk_governance:
            r = state.risk_governance
            sections.append("CURRENT RISK STATE:")
            sections.append(f"  {r.overall_governance_health}")

            for block_name, block_text in r.analysis_blocks.items():
                sections.append(f"  {block_name}: {block_text}")
            sections.append("")

        if state.synthesis and state.synthesis.key_risk_dashboard:
            sections.append("CURRENT RISK DASHBOARD:")
            for k, v in state.synthesis.key_risk_dashboard.items():
                sections.append(f"  {k}: {v}")
            sections.append("")

        if state.synthesis and state.synthesis.dynamic_investment_pillars:
            sections.append("CURRENT INVESTMENT PILLARS:")
            for p_name, p_data in state.synthesis.dynamic_investment_pillars.items():
                sections.append(f"  {p_name}: {p_data.thesis}")
            sections.append("")

        sections.append("═══ YOUR TASK ═══")
        sections.append(
            "Return a JSON object with EXACTLY these fields and no others:\n"
            "{\n"
            '  "changed_risk_dashboard": {},\n'
            '    // Dict[str, str] — only the risk entries that changed.\n'
            '    // Keys are the exact risk names from CURRENT RISK DASHBOARD above.\n'
            '    // Values are the new severity strings: "Low", "Medium", "High", "Elevated", "Critical".\n'
            '    // Empty dict if no risk entries changed.\n'
            '  "changed_pillars": {},\n'
            '    // Dict[str, str] — only the pillars that changed.\n'
            '    // Keys are exact pillar names from CURRENT INVESTMENT PILLARS above.\n'
            '    // Values are the new thesis strings.\n'
            '    // Empty dict if no pillars changed.\n'
            '  "changed_analysis_blocks": {},\n'
            '    // Dict[str, str] — only the analysis block entries that changed.\n'
            '    // Keys are the exact block names from CURRENT QUANTITATIVE STATE above.\n'
            '    // Empty dict if no analysis blocks changed.\n'
            '  "patch_summary": ""\n'
            '    // One sentence confirming what was updated.\n'
            "}\n"
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


    def _build_state_patch(
        self,
        parsed: dict,
        state: SharedState
    ) -> "StatePatch":
        """
        Converts the LLM's patch JSON into a StatePatch object.
        Assembles changed_paths from the three change dicts.
        Calls manifest_builder to produce patch_manifest for
        only the sections that changed.
        """
        from src.agents.base.shared_state import StatePatch
        changed_paths: Dict[str, Any] = {}

        # ── Risk dashboard changes ──
        changed_risk = parsed.get("changed_risk_dashboard", {})
        if isinstance(changed_risk, dict):
            new_dashboard = None
            if state.synthesis and state.synthesis.key_risk_dashboard is not None:
                new_dashboard = dict(state.synthesis.key_risk_dashboard)
                
            for risk_name, new_val in changed_risk.items():
                changed_paths[f"synthesis.key_risk_dashboard.{risk_name}"] = new_val
                if new_dashboard is not None:
                    new_dashboard[risk_name] = new_val
                    
            if new_dashboard is not None:
                state.synthesis = state.synthesis.model_copy(update={"key_risk_dashboard": new_dashboard})

        # ── Pillar changes ──
        changed_pillars = parsed.get("changed_pillars", {})
        if isinstance(changed_pillars, dict):
            new_pillars = None
            if state.synthesis and state.synthesis.dynamic_investment_pillars is not None:
                new_pillars = dict(state.synthesis.dynamic_investment_pillars)
                
            for pillar_name, new_thesis in changed_pillars.items():
                changed_paths[f"synthesis.dynamic_investment_pillars.{pillar_name}.thesis"] = new_thesis
                if new_pillars is not None and pillar_name in new_pillars:
                    old_pillar = new_pillars[pillar_name]
                    new_pillars[pillar_name] = old_pillar.model_copy(update={"thesis": new_thesis})
                    
            if new_pillars is not None:
                state.synthesis = state.synthesis.model_copy(update={"dynamic_investment_pillars": new_pillars})

        # ── Analysis block changes ──
        changed_blocks = parsed.get("changed_analysis_blocks", {})
        if isinstance(changed_blocks, dict):
            new_blocks = None
            if state.quantitative and state.quantitative.analysis_blocks is not None:
                new_blocks = dict(state.quantitative.analysis_blocks)
                
            for block_name, new_text in changed_blocks.items():
                changed_paths[f"quantitative_result.data.analysis_blocks.{block_name}"] = new_text
                if new_blocks is not None:
                    new_blocks[block_name] = new_text
                    
            if new_blocks is not None:
                new_quant = state.quantitative.model_copy(update={"analysis_blocks": new_blocks})
                state.quantitative_result = state.quantitative_result.model_copy(update={"data": new_quant})

        # ── Patch manifest: only changed sections ──
        patch_manifest = None
        try:
            from src.agents.synthesizer.manifest_builder import (
                build_risk_dashboard_section,
                build_investment_pillars_section,
                build_key_ratios_section,
            )
            changed_sections: Dict[str, List] = {}

            if changed_risk:
                risk_components = build_risk_dashboard_section(state)
                if risk_components:
                    changed_sections["risk_dashboard"] = risk_components

            if changed_pillars:
                pillar_components = build_investment_pillars_section(state)
                if pillar_components:
                    changed_sections["investment_pillars"] = pillar_components

            if changed_blocks:
                ratio_components = build_key_ratios_section(state)
                if ratio_components:
                    changed_sections["key_ratios"] = ratio_components

            if changed_sections:
                patch_manifest = changed_sections

        except Exception as e:
            logger.warning(
                f"[{self.agent_name}] patch_manifest build failed (non-fatal): {e}"
            )
            patch_manifest = None

        return StatePatch(
            changed_paths=changed_paths,
            patch_manifest=patch_manifest,
            patch_summary=parsed.get("patch_summary", "Dashboard updated."),
        )

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

        response_type = (
            state.execution_plan.response_type
            if state.execution_plan
            else ResponseType.DASHBOARD
        )

        if response_type == ResponseType.PATCH:
            # Does NOT go through SynthesizerOutput validation
            # Handled entirely by _build_state_patch
            try:
                state_patch = self._build_state_patch(parsed, state)
                state.state_patch = state_patch

                # ── Build final_thesis for the chat panel ──
                md = f"## Update Applied\n{state_patch.patch_summary}\n"
                if state_patch.changed_paths:
                    md += "\n**Changed fields:**\n"
                    for path in state_patch.changed_paths:
                        md += f"- `{path}`\n"

                state.final_thesis = md
                logger.info(
                    f"[{self.agent_name}] StatePatch built — "
                    f"{len(state_patch.changed_paths)} changed paths, "
                    f"patch_manifest sections: "
                    f"{list(state_patch.patch_manifest.keys()) if state_patch.patch_manifest else []}"
                )

            except Exception as e:
                logger.error(f"[{self.agent_name}] StatePatch build failed: {e}")
                state.state_patch = None
                md = f"## Update Applied\n{parsed.get('patch_summary', 'Dashboard updated.')}\n"
                state.final_thesis = md

        else:
            # Dashboard and chat both go through SynthesizerOutput validation
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

            if response_type == ResponseType.CHAT:
                md = f"## Answer\n{synth_out.targeted_answer or synth_out.executive_summary}\n"

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

            # ─── Step 10: UIManifest generation (dashboard mode only) ───
            if response_type == ResponseType.DASHBOARD:
                try:
                    from src.agents.synthesizer.manifest_builder import build_ui_manifest
                    state.ui_manifest = build_ui_manifest(state)
                    logger.info(
                        f"[{self.agent_name}] UIManifest built — "
                        f"{sum(len(v) for v in state.ui_manifest.layout_sections.values())} components "
                        f"across {len(state.ui_manifest.layout_sections)} sections"
                    )
                except Exception as e:
                    logger.warning(f"[{self.agent_name}] UIManifest generation failed (non-fatal): {e}")
                    state.ui_manifest = None
                    # Do NOT fail the agent — manifest failure is non-fatal


        state.agent_statuses[self.agent_name] = "completed"
        logger.info(
            f"[{self.agent_name}] Done — "
            f"verdict: {state.investment_verdict} "
            f"confidence: {state.confidence_level}"
        )
        return state


synthesizer = SynthesizerAgent()
