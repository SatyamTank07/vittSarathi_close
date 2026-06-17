import pytest
from unittest.mock import AsyncMock, patch

from src.agents.base.shared_state import (
    SharedState,
    AgentResult,
    ExecutionPlan,
    ResponseType,
    QuantitativeOutput,
    QualitativeOutput,
    SynthesizerOutput,
    InvestmentDecision
)
from src.agents.synthesizer.agent import SynthesizerAgent

@pytest.fixture
def base_state():
    return SharedState(
        user_query="Analyze TCS",
        ticker="TCS.NS",
        company_name="Tata Consultancy Services",
        industry="IT",
        sector="Tech",
        currency="INR"
    )

def test_build_caveat_block_missing(base_state):
    """Test that missing agents produce a MISSING DATA warning."""
    agent = SynthesizerAgent()
    
    # quantitative is None by default
    base_state.qualitative_result = AgentResult(status="success")
    base_state.risk_governance_result = AgentResult(status="success")
    base_state.sentiment_result = AgentResult(status="success")
    
    caveat = agent._build_caveat_block(base_state)
    assert "MISSING DATA: quantitative produced NO output." in caveat

def test_build_caveat_block_partial(base_state):
    """Test that partial agents produce a PARTIAL DATA warning."""
    agent = SynthesizerAgent()
    
    base_state.quantitative_result = AgentResult(status="success")
    base_state.qualitative_result = AgentResult(status="partial")
    base_state.risk_governance_result = AgentResult(status="success")
    base_state.sentiment_result = AgentResult(status="success")
    
    caveat = agent._build_caveat_block(base_state)
    assert "PARTIAL DATA: qualitative returned incomplete output." in caveat

def test_prompt_builders_branching(base_state):
    """Test that the correct prompt builder is called based on response_type."""
    agent = SynthesizerAgent()
    
    # 1. Default (DASHBOARD)
    base_state.execution_plan = ExecutionPlan(
        primary_agents=["synthesizer"],
        response_type=ResponseType.DASHBOARD
    )
    prompt = agent._build_prompt(base_state)
    assert "═══ YOUR TASK ═══" in prompt
    assert "Synthesize the above into a cohesive investment thesis." in prompt

    # 2. CHAT
    base_state.execution_plan.response_type = ResponseType.CHAT
    prompt = agent._build_prompt(base_state)
    assert "YOU ARE IN CHAT MODE." in prompt

    # 3. PATCH
    base_state.execution_plan.response_type = ResponseType.PATCH
    prompt = agent._build_prompt(base_state)
    assert "YOU ARE IN PATCH MODE." in prompt

@pytest.mark.asyncio
@patch("src.agents.synthesizer.agent.SynthesizerAgent._get_llm")
async def test_synthesizer_execute_dashboard(mock_get_llm, base_state):
    """Test full execution flow for a dashboard request."""
    agent = SynthesizerAgent()
    
    base_state.execution_plan = ExecutionPlan(
        primary_agents=["synthesizer"],
        response_type=ResponseType.DASHBOARD
    )
    
    # Mock LLM Response
    mock_llm_instance = AsyncMock()
    mock_llm_instance.ainvoke.return_value.content = """```json
    {
        "agent": "synthesizer_cio",
        "investment_decision": {
            "final_rating": "Buy",
            "conviction_score": 0.85,
            "target_horizon": "Long term"
        },
        "executive_summary": "TCS is a solid buy due to strong margins.",
        "conflict_resolution_log": [],
        "dynamic_investment_pillars": {
            "financial_health": {
                "thesis": "Strong",
                "supporting_metrics": [
                    {"metric": "PE", "value": "25", "status": "Good"}
                ]
            }
        },
        "key_risk_dashboard": {
            "currency_risk": "Medium"
        },
        "final_sign_off": true
    }
    ```"""
    mock_get_llm.return_value = mock_llm_instance
    
    result_state = await agent.execute(base_state)
    
    assert result_state.agent_statuses["synthesizer"] == "completed"
    assert result_state.investment_verdict == "Buy"
    assert result_state.confidence_level == "0.85"
    assert "## Executive Summary" in result_state.final_thesis
    assert "TCS is a solid buy" in result_state.final_thesis
    assert "## Investment Pillars" in result_state.final_thesis
    assert "Financial Health" in result_state.final_thesis
    assert "## Risk Dashboard" in result_state.final_thesis

@pytest.mark.asyncio
@patch("src.agents.synthesizer.agent.SynthesizerAgent._get_llm")
async def test_synthesizer_execute_chat(mock_get_llm, base_state):
    """Test execution flow for a chat follow-up."""
    agent = SynthesizerAgent()
    
    base_state.execution_plan = ExecutionPlan(
        primary_agents=["synthesizer"],
        response_type=ResponseType.CHAT
    )
    
    # Mock LLM Response
    mock_llm_instance = AsyncMock()
    mock_llm_instance.ainvoke.return_value.content = """
    {
        "agent": "synthesizer_cio",
        "targeted_answer": "TCS has strong margins mainly because of its large scale.",
        "executive_summary": "TCS margin explanation."
    }
    """
    mock_get_llm.return_value = mock_llm_instance
    
    result_state = await agent.execute(base_state)
    
    assert result_state.agent_statuses["synthesizer"] == "completed"
    assert result_state.investment_verdict == "Targeted Response"
    assert "## Answer" in result_state.final_thesis
    assert "TCS has strong margins" in result_state.final_thesis
