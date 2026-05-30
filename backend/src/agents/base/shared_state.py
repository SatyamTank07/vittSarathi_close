"""
Shared State — Central data structures passed between agents.
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


# ─── Task Allocation Models (Orchestrator → Sub-Agents) ───

class OrchestrationMeta(BaseModel):
    ticker: str
    company_name: str
    sector: str
    industry: str
    routing_framework: str

class QuantitativeAllocation(BaseModel):
    focus_metrics: List[str] = Field(default_factory=list)
    valuation_methodology: str = ""
    historical_depth_years: int = 5

class QualitativeAllocation(BaseModel):
    rag_target_topics: List[str] = Field(default_factory=list)
    competitive_moat_criteria: str = ""

class RiskGovernanceAllocation(BaseModel):
    risk_vectors_to_score: List[str] = Field(default_factory=list)
    compliance_benchmarks: str = ""

class TaskAllocations(BaseModel):
    agent_2_quantitative: QuantitativeAllocation = Field(default_factory=QuantitativeAllocation)
    agent_3_qualitative: QualitativeAllocation = Field(default_factory=QualitativeAllocation)
    agent_4_risk_governance: RiskGovernanceAllocation = Field(default_factory=RiskGovernanceAllocation)

class OrchestratorOutput(BaseModel):
    orchestration_meta: OrchestrationMeta
    task_allocations: TaskAllocations


# ─── Agent Output Models ───

class QuantitativeOutput(BaseModel):
    revenue_trend: str
    profit_margin_analysis: str
    valuation_assessment: str
    health_metrics: str
    sector_specific: str
    raw_ratios: Dict[str, Any] = Field(default_factory=dict)

class QualitativeOutput(BaseModel):
    moat_analysis: str
    management_quality: str
    growth_catalysts: str
    business_model: str
    narrative_explanation: str

class RiskGovernanceOutput(BaseModel):
    red_flags: List[str] = Field(default_factory=list)
    governance_score: str
    structural_risks: str
    insider_activity: str
    overall_risk_level: str


class SharedState(BaseModel):
    """
    The master state object that holds all context and results for a single analysis run.
    """
    # ─── Orchestrator Inputs (Context) ───
    ticker: str
    company_name: str
    industry: str
    sector: str
    currency: str
    current_price: Optional[float] = None
    summary: str = ""
    routing_framework: str = ""
    industry_instructions: Dict[str, str] = Field(default_factory=dict)
    stock_data: Dict[str, Any] = Field(default_factory=dict)

    # ─── Orchestrator Task Allocations ───
    task_allocations: Optional[TaskAllocations] = None

    # ─── Agent Outputs ───
    quantitative: Optional[QuantitativeOutput] = None
    qualitative: Optional[QualitativeOutput] = None
    risk_governance: Optional[RiskGovernanceOutput] = None

    # ─── Final Synthesis ───
    final_thesis: str = ""
    investment_verdict: str = "Neutral"
    confidence_level: str = "Low"

    # Tracking
    agent_statuses: Dict[str, str] = Field(default_factory=dict)

