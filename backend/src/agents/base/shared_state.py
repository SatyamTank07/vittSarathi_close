"""
Shared State — Central data structures passed between agents.
"""

from enum import Enum
from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field, ConfigDict


# ─── Task Allocation Models (Orchestrator → Sub-Agents) ───

class OrchestrationMeta(BaseModel):
    ticker: str
    company_name: str
    sector: str
    industry: str
    routing_framework: str
    confidence_score: float = Field(default=1.0, description="Confidence score from 0.0 to 1.0 for the extracted entity.")
    disambiguation_candidates: List[Dict[str, str]] = Field(
        default_factory=list, 
        description="If confidence is < 0.8, provide a list of dicts with 'ticker' and 'company_name' for the top 3 candidates."
    )

class ResponseType(str, Enum):
    DASHBOARD = "dashboard"
    CHAT      = "chat"
    PATCH     = "patch"


class AgentExecution(BaseModel):
    """
    Describes whether a single agent should run, what to focus on,
    which sub-agents to invoke, and why the orchestrator made this choice.
    """
    should_run: bool = False

    focus: List[str] = Field(
        default_factory=list,
        description=(
            "What this agent should focus on for this specific query. "
            "Replaces the old focus_metrics / rag_target_topics / risk_vectors fields."
        )
    )

    sub_agents: List[str] = Field(
        default_factory=list,
        description=(
            "Names of sub-agents to run under this agent. "
            "Must match keys in AGENT_REGISTRY. Empty list = run no sub-agents."
        )
    )

    reasoning: str = Field(
        default="",
        description="Why the orchestrator chose to run or skip this agent."
    )


class ExecutionPlan(BaseModel):
    """
    The Orchestrator's complete decision for a single query.
    Replaces TaskAllocations. Contains response routing + per-agent decisions.
    """
    response_type: ResponseType = ResponseType.DASHBOARD

    agents: Dict[str, AgentExecution] = Field(
        default_factory=dict,
        description=(
            "Keys are agent names matching AGENT_REGISTRY: "
            "'quantitative', 'qualitative', 'risk_governance', 'sentiment'. "
            "Values describe whether and how each agent should run."
        )
    )

    overall_reasoning: str = Field(
        default="",
        description="One sentence from the orchestrator explaining the overall plan."
    )

class OrchestratorOutput(BaseModel):
    orchestration_meta: OrchestrationMeta
    execution_plan: ExecutionPlan

class OrchestratorOutputV2(BaseModel):
    """
    New orchestrator output schema.
    Replaces OrchestratorOutput after Step 4.
    """
    orchestration_meta: OrchestrationMeta   # reuse existing — no changes needed
    execution_plan: ExecutionPlan           # new — replaces task_allocations

class AgentResult(BaseModel):
    """
    Wraps every agent output with health metadata.
    pipeline.py stores these, Synthesizer reads them to know
    what data is trustworthy and what to caveat.
    """
    data: Optional[Any] = None
    status: Literal["success", "partial", "failed"] = "failed"
    error: Optional[str] = None
    data_quality: Literal["high", "medium", "low", "unavailable"] = "unavailable"
    fallback_used: bool = False
    agent_name: str = ""

# ─── Agent Output Models ───

class QuantitativeOutput(BaseModel):
    industry_framework_used: str = Field(
        description="The specific industry framework applied (e.g., 'SaaS', 'Banking', 'Energy')"
    )
    analysis_blocks: Dict[str, str] = Field(
        description="Dynamic key-value pairs. Keys are the specific metrics analyzed (e.g., 'Net Interest Margin', 'ARPU Growth', 'Gross Refining Margin'). Values are the detailed analysis."
    )
    raw_ratios: Dict[str, Any] = Field(
        default_factory=dict,
        description="The raw numerical data fetched from the tools to back up the analysis."
    )
    overall_quantitative_health: str = Field(
        description="A short concluding summary of the quantitative health of the company."
    )

class QualitativeOutput(BaseModel):
    moat_analysis: str
    management_quality: str
    growth_catalysts: str
    business_model: str
    narrative_explanation: str

class RiskGovernanceOutput(BaseModel):
    industry_framework_used: str = Field(
        description="The specific industry framework applied (e.g., 'Banking', 'Tech', 'Energy')"
    )
    analysis_blocks: Dict[str, str] = Field(
        description="Dynamic key-value pairs. Keys are the specific risk factors analyzed (e.g., 'Promoter Pledging & RPT', 'Auditor & Board Independence'). Values are the detailed analysis."
    )
    raw_metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="The raw numerical data, ML scores, and nested flags fetched from the tools."
    )
    overall_governance_health: str = Field(
        description="A short concluding summary by the Internal Investigator regarding structural risks."
    )

class MarketSentiment(BaseModel):
    overall_mood: str = Field(description="E.g., Positive, Neutral, Negative")
    finbert_score_breakdown: Dict[str, int] = Field(
        default_factory=dict,
        description="Optional breakdown of sentiment percentages, e.g., {'positive': 72, 'negative': 15, 'neutral': 13}"
    )
    dominant_news_themes: List[str] = Field(default_factory=list)

class MacroeconomicEnvironment(BaseModel):
    source: str = Field(default="Various APIs")
    metrics: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Dynamic dictionary. Keys are metric names (e.g. 'inflation'), values are dicts with 'current_value', 'trend', and 'business_impact'."
    )

class SectorFactors(BaseModel):
    tailwinds: List[str] = Field(default_factory=list, description="List of positive dynamic tailwinds for this sector")
    headwinds: List[str] = Field(default_factory=list, description="List of negative dynamic headwinds for this sector")

class SentimentOutput(BaseModel):
    market_sentiment: MarketSentiment
    macroeconomic_environment: MacroeconomicEnvironment
    sector_factors: SectorFactors

class ComponentType(str, Enum):
    METRIC_CARD     = "metric_card"      # single KPI number + label + status
    PILLAR_CARD     = "pillar_card"      # thesis string + supporting metrics list
    RISK_CARD       = "risk_card"        # risk name + Low/Medium/High/Elevated value
    SENTIMENT_BLOCK = "sentiment_block"  # mood badge + themes list
    TEXT_BLOCK      = "text_block"       # free text — exec summary, thesis paragraph
    MACRO_BLOCK     = "macro_block"      # key-value macro indicators

class ComponentSize(str, Enum):
    SMALL  = "small"   # 1 column — single KPI
    MEDIUM = "medium"  # 2 columns — pillar card, risk item
    LARGE  = "large"   # 3 columns — sentiment, summary
    FULL   = "full"    # full width — conflict log, thesis text

class UIComponent(BaseModel):
    id:             str            # unique snake_case identifier e.g. "metric_nim"
    component_type: ComponentType
    size:           ComponentSize
    data_path:      str            # dot-notation path into SharedState
    label:          str            # display label shown on card
    status:         Optional[str] = None   # "green" | "yellow" | "red" | None
    order:          int            # render position within its section

class UIManifest(BaseModel):
    layout_sections: Dict[str, List[UIComponent]]
    # Keys are section names the frontend uses as headings:
    # "key_ratios", "investment_pillars", "risk_dashboard",
    # "sentiment", "executive_summary"
    # Values are ordered lists of UIComponent

class SharedState(BaseModel):
    """
    The master state object that holds all context and results for a single analysis run.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # ─── Orchestrator Inputs (Context) ───
    user_query: Optional[str] = None
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
    clarification_needed: bool = False
    disambiguation_candidates: List[Dict[str, str]] = Field(default_factory=list)

    # ─── Orchestrator Task Allocations ───
    execution_plan: Optional[ExecutionPlan] = None
    session_id: str = Field(
        default="",
        description="Ties a chat conversation to a specific dashboard instance."
    )
    has_existing_dashboard: bool = Field(
        default=False,
        description="True after the first full dashboard analysis has been returned to the frontend."
    )

    # ─── Agent Outputs ───
    quantitative_result: Optional[AgentResult] = None
    qualitative_result: Optional[AgentResult] = None
    risk_governance_result: Optional[AgentResult] = None
    sentiment_result: Optional[AgentResult] = None

    sub_agent_results: Dict[str, AgentResult] = Field(
        default_factory=dict,
        description=(
            "Namespaced sub-agent outputs. "
            "Keys follow pattern '<primary_agent>.<sub_agent_name>' "
            "e.g. 'quantitative.dcf_modeller', 'risk_governance.litigation_scanner'. "
            "Written by primary agents after their sub-agents complete."
        )
    )

    @property
    def quantitative(self) -> Optional[QuantitativeOutput]:
        return self.quantitative_result.data if self.quantitative_result else None

    @property
    def qualitative(self) -> Optional[QualitativeOutput]:
        return self.qualitative_result.data if self.qualitative_result else None

    @property
    def risk_governance(self) -> Optional[RiskGovernanceOutput]:
        return self.risk_governance_result.data if self.risk_governance_result else None

    @property
    def sentiment(self) -> Optional[SentimentOutput]:
        return self.sentiment_result.data if self.sentiment_result else None

    # ─── Final Synthesis ───
    final_thesis: str = ""
    investment_verdict: str = "Neutral"
    confidence_level: str = "Low"
    synthesis: Optional['SynthesizerOutput'] = None
    ui_manifest: Optional[UIManifest] = None

    # Tracking
    agent_statuses: Dict[str, str] = Field(default_factory=dict)

class InvestmentDecision(BaseModel):
    final_rating: str
    conviction_score: float
    target_horizon: str

class ConflictResolution(BaseModel):
    conflict_identified: str
    severity: str
    synthesized_resolution: str

class PillarMetric(BaseModel):
    metric: str
    value: str
    status: str

class InvestmentPillar(BaseModel):
    thesis: str
    supporting_metrics: List[PillarMetric] = Field(default_factory=list)

class SynthesizerOutput(BaseModel):
    agent: str = "synthesizer_cio"
    targeted_answer: Optional[str] = Field(default=None, description="Populated for highly specific user queries instead of a full investment decision")
    investment_decision: Optional[InvestmentDecision] = None
    executive_summary: str
    conflict_resolution_log: List[ConflictResolution] = Field(default_factory=list)
    dynamic_investment_pillars: Optional[Dict[str, InvestmentPillar]] = Field(default_factory=dict)
    key_risk_dashboard: Optional[Dict[str, str]] = Field(default_factory=dict)
    final_sign_off: bool = False

SharedState.model_rebuild()
