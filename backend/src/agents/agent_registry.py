# agent_registry.py
"""
AGENT_REGISTRY — Single source of truth for all agents and sub-agents.

This file is read by:
  - orchestrator_agent.py  : injects available agent/sub-agent names into the LLM prompt
  - pipeline.py            : uses class references to instantiate agents at runtime

Rules:
  - Do NOT put any logic here
  - Do NOT import SharedState or any pipeline code here
  - Agent class references are forward-declared as strings now,
    swapped to real imports in Step 6
"""

from dataclasses import dataclass, field
from typing import Dict, Type, Optional

from src.agents.quantitative.agent import QuantitativeAgent
from src.agents.quantitative.sub_agents.dcf_modeller import DCFModellerAgent
from src.agents.quantitative.sub_agents.peer_comparator import PeerComparatorAgent
from src.agents.quantitative.sub_agents.segment_splitter import SegmentSplitterAgent

from src.agents.qualitative.agent import QualitativeAgent
from src.agents.qualitative.sub_agents.mgmt_tracker import MgmtTrackerAgent
from src.agents.qualitative.sub_agents.moat_scorer import MoatScorerAgent
from src.agents.qualitative.sub_agents.capex_intent import CapexIntentAgent

from src.agents.risk_and_governance.agent import RiskGovernanceAgent
from src.agents.risk_and_governance.sub_agents.litigation_scanner import LitigationScannerAgent
from src.agents.risk_and_governance.sub_agents.promoter_history import PromoterHistoryAgent
from src.agents.risk_and_governance.sub_agents.related_party import RelatedPartyAgent

from src.agents.sentiment_and_macro_analyst.agent import SentimentAndMacroAgent
from src.agents.sentiment_and_macro_analyst.sub_agents.fii_dii_tracker import FIIDIITrackerAgent
from src.agents.sentiment_and_macro_analyst.sub_agents.sector_rotation import SectorRotationAgent
from src.agents.sentiment_and_macro_analyst.sub_agents.news_sentiment import NewsSentimentAgent


@dataclass
class SubAgentMeta:
    """Describes a single sub-agent entry in the registry."""

    name: str
    description: str
    # What kind of query justifies running this sub-agent.
    # Orchestrator reads this to decide whether to include it.
    trigger_hint: str
    # Placeholder — real class reference added in Step 6
    agent_class: Optional[object] = None


@dataclass
class PrimaryAgentMeta:
    """Describes a single primary agent and its available sub-agents."""

    name: str
    description: str
    # One-line role label shown to the Orchestrator LLM
    role: str
    sub_agents: Dict[str, SubAgentMeta] = field(default_factory=dict)
    # Placeholder — real class reference added in Step 6
    agent_class: Optional[object] = None


# ─────────────────────────────────────────────
# THE REGISTRY
# ─────────────────────────────────────────────

AGENT_REGISTRY: Dict[str, PrimaryAgentMeta] = {

    "quantitative": PrimaryAgentMeta(
        name="quantitative",
        role="The Accountant",
        description=(
            "Deep financial ratio analysis, valuation, and margin trends. "
            "Reads balance sheets, P&L statements, cash flow data. "
            "Run for any query involving numbers, ratios, valuation, or financial health."
        ),
        sub_agents={
            "dcf_modeller": SubAgentMeta(
                name="dcf_modeller",
                description="Builds a discounted cash flow model using free cash flow projections.",
                trigger_hint="Run when user asks for intrinsic value, fair value, or DCF.",
                agent_class=DCFModellerAgent
            ),
            "peer_comparator": SubAgentMeta(
                name="peer_comparator",
                description="Fetches the same key ratios for 3-5 sector peers and compares them side by side.",
                trigger_hint="Run when user asks how this company compares to competitors or sector average.",
                agent_class=PeerComparatorAgent
            ),
            "segment_splitter": SubAgentMeta(
                name="segment_splitter",
                description="Breaks down revenue and margin by business segment or division.",
                trigger_hint="Run when user asks about segment performance, division-level revenue, or business mix.",
                agent_class=SegmentSplitterAgent
            ),
        },
        agent_class=QuantitativeAgent
    ),

    "qualitative": PrimaryAgentMeta(
        name="qualitative",
        role="The Strategist",
        description=(
            "Evaluates business moats, narrative disclosures, and management commentary. "
            "Reads MDA sections, directors reports, and concall transcripts. "
            "Run for any query involving strategy, management quality, competitive position, or growth narrative."
        ),
        sub_agents={
            "mgmt_tracker": SubAgentMeta(
                name="mgmt_tracker",
                description="Runs NLP on earnings call transcripts to detect tone shifts, commitment tracking, and guidance accuracy.",
                trigger_hint="Run when user asks about management credibility, concall commentary, or guidance history.",
                agent_class=MgmtTrackerAgent
            ),
            "moat_scorer": SubAgentMeta(
                name="moat_scorer",
                description="Scores the company's competitive moat across Porter's 5 forces framework.",
                trigger_hint="Run when user asks about competitive advantage, moat strength, or industry position.",
                agent_class=MoatScorerAgent
            ),
            "capex_intent": SubAgentMeta(
                name="capex_intent",
                description="Extracts forward-looking capex commitments and expansion signals from disclosures.",
                trigger_hint="Run when user asks about growth plans, capacity expansion, or future investments.",
                agent_class=CapexIntentAgent
            ),
        },
        agent_class=QualitativeAgent
    ),

    "risk_governance": PrimaryAgentMeta(
        name="risk_governance",
        role="The Investigator",
        description=(
            "Skeptical investigation of red flags, regulatory threats, and governance issues. "
            "Reads auditor reports, SEBI filings, insider trading forms, and board composition data. "
            "Run for any query involving risk, governance, promoters, auditors, or regulatory compliance."
        ),
        sub_agents={
            "litigation_scanner": SubAgentMeta(
                name="litigation_scanner",
                description="Scans for active court cases, SEBI orders, regulatory penalties, and contingent liabilities.",
                trigger_hint="Run when user asks about legal risk, SEBI action, penalties, or litigation exposure.",
                agent_class=LitigationScannerAgent
            ),
            "promoter_history": SubAgentMeta(
                name="promoter_history",
                description="Tracks promoter pledge percentage trend over 5 years, detects QoQ changes and creeping acquisitions.",
                trigger_hint="Run when user asks about promoter holding, pledge history, or insider confidence.",
                agent_class=PromoterHistoryAgent
            ),
            "related_party": SubAgentMeta(
                name="related_party",
                description="Analyses related party transactions for anomalies, tunnelling patterns, and threshold breaches.",
                trigger_hint="Run when user asks about RPT, related party risk, or fund diversion concerns.",
                agent_class=RelatedPartyAgent
            ),
        },
        agent_class=RiskGovernanceAgent
    ),

    "sentiment": PrimaryAgentMeta(
        name="sentiment",
        role="The Pulse Reader",
        description=(
            "Analyses market mood, news sentiment, and macroeconomic trends affecting the sector. "
            "Reads RSS feeds, RBI/FRED macro indicators, and NSE/BSE announcements. "
            "Run for any query involving market sentiment, macro environment, sector tailwinds, or news impact."
        ),
        sub_agents={
            "fii_dii_tracker": SubAgentMeta(
                name="fii_dii_tracker",
                description="Tracks FII and DII institutional flow data to detect smart money movement.",
                trigger_hint="Run when user asks about institutional buying/selling, FII flows, or DII activity.",
                agent_class=FIIDIITrackerAgent
            ),
            "sector_rotation": SubAgentMeta(
                name="sector_rotation",
                description="Measures relative strength of this sector vs broader market using RSI and flow data.",
                trigger_hint="Run when user asks about sector momentum, rotation, or relative performance.",
                agent_class=SectorRotationAgent
            ),
            "news_sentiment": SubAgentMeta(
                name="news_sentiment",
                description="Runs FinBERT NLP on recent headlines to produce a structured sentiment score breakdown.",
                trigger_hint="Run when user asks about recent news, market mood, or sentiment score.",
                agent_class=NewsSentimentAgent
            ),
        },
        agent_class=SentimentAndMacroAgent
    ),

}


# ─────────────────────────────────────────────
# UTILITY FUNCTIONS
# ─────────────────────────────────────────────

def get_orchestrator_menu() -> str:
    """
    Returns a formatted string injected into the Orchestrator's prompt.
    Tells the LLM exactly what agents and sub-agents are available,
    and when each should be triggered.
    Used in: orchestrator_agent.py (Step 4)
    """
    lines = []
    for agent_name, agent_meta in AGENT_REGISTRY.items():
        lines.append(f"\nAgent: {agent_name} ({agent_meta.role})")
        lines.append(f"  Description: {agent_meta.description}")
        lines.append(f"  Sub-agents:")
        for sub_name, sub_meta in agent_meta.sub_agents.items():
            lines.append(f"    - {sub_name}: {sub_meta.description}")
            lines.append(f"      Trigger: {sub_meta.trigger_hint}")
    return "\\n".join(lines)


def get_agent_names() -> list[str]:
    """
    Returns the list of primary agent name keys.
    Used in: pipeline.py (Step 3) to validate ExecutionPlan keys.
    """
    return list(AGENT_REGISTRY.keys())


def get_sub_agent_names(agent_name: str) -> list[str]:
    """
    Returns valid sub-agent names for a given primary agent.
    Used in: pipeline.py (Step 3) to validate sub-agent lists before running.
    """
    if agent_name not in AGENT_REGISTRY:
        raise KeyError(f"Agent '{agent_name}' not found in AGENT_REGISTRY.")
    return list(AGENT_REGISTRY[agent_name].sub_agents.keys())
