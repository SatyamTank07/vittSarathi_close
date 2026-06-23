"""
API response schemas — typed contracts for the frontend.

Three response shapes:
    DashboardResponse  — full analysis, all components populated
    ChatResponse       — single targeted answer, dashboard unchanged
    PatchResponse      — partial card update, diff only

One request shape:
    AnalyzeRequest     — replaces the simple {"query": "..."} shape
"""

from typing import Optional, Any
from pydantic import BaseModel, Field


# ─── Request ────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    query: str
    session_id: Optional[str] = Field(
        default=None,
        description=(
            "Session ID from a prior dashboard response. "
            "If provided, backend loads prior SharedState for chat/patch modes. "
            "If None or unrecognised, a new session is created."
        )
    )
    existing_state_hash: Optional[str] = Field(
        default=None,
        description=(
            "MD5 hash of the SharedState JSON the frontend currently holds. "
            "Used to detect stale state — if hashes differ the backend "
            "returns a full dashboard refresh instead of a patch."
        )
    )


# ─── Shared sub-models ──────────────────────────────────────

class AgentStatusMap(BaseModel):
    """Status of each agent in the pipeline run."""
    orchestrator: Optional[str] = None
    quantitative: Optional[str] = None
    qualitative: Optional[str] = None
    risk_governance: Optional[str] = None
    sentiment: Optional[str] = None
    synthesizer: Optional[str] = None


# ─── Three response shapes ──────────────────────────────────

class DashboardResponse(BaseModel):
    """
    Returned when response_type == 'dashboard'.
    All analysis fields are populated.
    Frontend replaces its full dashboard state with this.
    """
    status: str = "success"
    response_type: str = "dashboard"
    session_id: str                        # frontend stores this for follow-up requests
    user_query: Optional[str] = None
    ticker: str
    company_name: str
    sector: str
    industry: str
    currency: str
    current_price: Optional[float] = None
    orchestrator_confidence: float
    investment_verdict: str
    confidence_level: str
    final_thesis: str
    quantitative: Optional[dict] = None
    qualitative: Optional[dict] = None
    risk_governance: Optional[dict] = None
    sentiment: Optional[dict] = None
    agent_statuses: dict = Field(default_factory=dict)
    ui_manifest: Optional[dict] = None
    state_patch: None = None               # always None for dashboard
    analysis_duration_seconds: float
    report_id: Optional[str] = None


class ChatResponse(BaseModel):
    """
    Returned when response_type == 'chat'.
    Only targeted_answer is populated. Dashboard state is unchanged.
    Frontend appends targeted_answer to the chat panel only.
    """
    status: str = "success"
    response_type: str = "chat"
    session_id: str                        # echoed back so frontend can confirm
    user_query: Optional[str] = None
    ticker: str
    company_name: str
    targeted_answer: str                   # the only new content
    investment_verdict: Optional[str] = None  # echoed from existing state
    agent_statuses: dict = Field(default_factory=dict)
    ui_manifest: None = None               # always None for chat
    state_patch: None = None               # always None for chat
    analysis_duration_seconds: float


class PatchResponse(BaseModel):
    """
    Returned when response_type == 'patch'.
    Only changed fields are populated via state_patch.
    Frontend merges state_patch.changed_paths into its existing state
    and re-renders only the affected cards.
    """
    status: str = "success"
    response_type: str = "patch"
    session_id: str
    user_query: Optional[str] = None
    ticker: str
    company_name: str
    investment_verdict: Optional[str] = None
    agent_statuses: dict = Field(default_factory=dict)
    ui_manifest: None = None               # always None for patch
    state_patch: Optional[dict] = None     # the only new content
    analysis_duration_seconds: float


class ClarificationResponse(BaseModel):
    """
    Returned when the orchestrator cannot confidently resolve the entity.
    No agents have run. Frontend shows candidate list in chat panel.
    """
    status: str = "clarification_needed"
    response_type: str = "dashboard"
    session_id: Optional[str] = None      # no session created yet
    user_query: Optional[str] = None
    ticker: str
    company_name: str
    sector: str
    industry: str
    currency: str
    current_price: Optional[float] = None
    orchestrator_confidence: float
    candidates: list[dict] = Field(default_factory=list)
    clarification_message: str            # human-readable prompt for the user
    investment_verdict: str = "Clarification Needed"
    confidence_level: str = "N/A"
    quantitative: None = None
    qualitative: None = None
    risk_governance: None = None
    sentiment: None = None
    agent_statuses: dict = Field(default_factory=dict)
    ui_manifest: None = None
    state_patch: None = None
    analysis_duration_seconds: float
