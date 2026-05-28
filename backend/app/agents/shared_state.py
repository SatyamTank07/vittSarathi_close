"""
Shared State — The centralized data structure all agents read/write.

This Pydantic model acts as the "whiteboard" that the Orchestrator creates,
the sub-agents populate, and the Synthesizer reads to produce the final report.
"""

from pydantic import BaseModel, Field
from typing import Optional


class QuantitativeOutput(BaseModel):
    """Output from Agent 2 — The Accountant."""
    revenue_trend: str = Field(description="'growing', 'declining', or 'stable' with brief rationale")
    profit_margin_analysis: str = Field(description="Analysis of profit margins and their trajectory")
    valuation_assessment: str = Field(description="PE, PB valuation analysis relative to sector")
    health_metrics: str = Field(description="Debt-to-equity, ROE, ROCE analysis")
    sector_specific: str = Field(description="Industry-adapted metrics (e.g., NIM for banks)")
    raw_ratios: dict = Field(default_factory=dict, description="Computed numeric ratios")


class QualitativeOutput(BaseModel):
    """Output from Agent 3 — The Business Strategist."""
    moat_analysis: str = Field(description="Competitive advantages and their durability")
    management_quality: str = Field(description="Assessment of leadership and capital allocation")
    growth_catalysts: str = Field(description="Future growth drivers and expansion plans")
    business_model: str = Field(description="Revenue model durability and diversification")
    narrative_explanation: str = Field(description="The 'why' behind the quantitative numbers")


class RiskGovernanceOutput(BaseModel):
    """Output from Agent 4 — The Internal Investigator."""
    red_flags: list[str] = Field(default_factory=list, description="List of specific warning signs")
    governance_score: str = Field(description="'strong', 'moderate', or 'weak'")
    structural_risks: str = Field(description="Share pledging, debt structure, concentration risks")
    insider_activity: str = Field(description="Insider buying/selling patterns and implications")
    overall_risk_level: str = Field(description="'low', 'medium', or 'high'")


class SharedState(BaseModel):
    """
    The centralized shared state document.
    
    Flow:
    1. Orchestrator creates it with metadata + stock_data
    2. Quantitative/Qualitative/Risk agents each write their output section
    3. Synthesizer reads everything and writes the final thesis
    """

    # --- Metadata (set by Orchestrator) ---
    ticker: str
    company_name: str
    industry: str = "Unknown"
    sector: str = "Unknown"
    currency: str = "USD"
    current_price: Optional[float] = None
    summary: str = ""
    industry_instructions: dict = Field(
        default_factory=dict,
        description="Sector-specific guidance for sub-agents from the Orchestrator"
    )

    # --- Raw data (fetched once via yfinance, shared across agents) ---
    stock_data: dict = Field(default_factory=dict)

    # --- Agent outputs (each agent writes to its own section) ---
    quantitative: Optional[QuantitativeOutput] = None
    qualitative: Optional[QualitativeOutput] = None
    risk_governance: Optional[RiskGovernanceOutput] = None

    # --- Synthesizer output ---
    final_thesis: Optional[str] = None           # Full Markdown report
    investment_verdict: Optional[str] = None      # "Bullish" | "Neutral" | "Bearish"
    confidence_level: Optional[str] = None        # "High" | "Medium" | "Low"

    # --- Status tracking ---
    agent_statuses: dict[str, str] = Field(
        default_factory=lambda: {
            "orchestrator": "pending",
            "quantitative": "pending",
            "qualitative": "pending",
            "risk_governance": "pending",
            "synthesizer": "pending",
        }
    )
