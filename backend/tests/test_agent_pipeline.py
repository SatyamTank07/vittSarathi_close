import pytest
import asyncio
from unittest.mock import patch, MagicMock
from pydantic import ValidationError

from src.agents.orchestrator.pipeline import (
    validate_execution_plan, 
    run_agent_safe,
    run_pipeline
)
from src.agents.base.shared_state import SharedState, ExecutionPlan, AgentExecution

# ---------------------------------------------------------
# Test: validate_execution_plan
# ---------------------------------------------------------

def test_validate_execution_plan():
    """Test that the validator flags unknown agents and sub-agents."""
    
    state = SharedState(
        user_query="test",
        ticker="TCS.NS",
        company_name="Tata Consultancy Services",
        industry="IT",
        sector="Tech",
        currency="INR",
        execution_plan=ExecutionPlan(
            response_type="dashboard",
            agents={
                "quantitative": AgentExecution(
                    should_run=True,
                    sub_agents=["dcf_modeller", "fake_sub_agent"]
                ),
                "fake_agent": AgentExecution(
                    should_run=True,
                    sub_agents=[]
                )
            }
        )
    )
    
    warnings = validate_execution_plan(state)
    
    assert len(warnings) == 2
    assert any("fake_agent" in w for w in warnings)
    assert any("fake_sub_agent" in w for w in warnings)

# ---------------------------------------------------------
# Test: run_agent_safe
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_run_agent_safe_timeout():
    """Test that timeouts are caught and returned as failed AgentResult."""
    
    async def slow_agent(state):
        await asyncio.sleep(2)
        return {"data": "too slow"}
        
    state = SharedState(
        user_query="test",
        ticker="TCS.NS",
        company_name="Tata",
        industry="IT",
        sector="Tech",
        currency="INR"
    )
    
    # We monkeypatch the timeout dict to force a quick timeout
    with patch("src.agents.orchestrator.pipeline.AGENT_TIMEOUTS", {"quantitative": 0.1}):
        result = await run_agent_safe(slow_agent, state, "quantitative")
        
    assert result.status == "failed"
    assert "timed out" in result.error
    assert result.data_quality == "unavailable"

@pytest.mark.asyncio
async def test_run_agent_safe_exception():
    """Test that arbitrary exceptions are caught safely."""
    
    async def buggy_agent(state):
        raise ValueError("Something broke deeply")
        
    state = SharedState(
        user_query="test",
        ticker="TCS.NS",
        company_name="Tata",
        industry="IT",
        sector="Tech",
        currency="INR"
    )
    
    result = await run_agent_safe(buggy_agent, state, "qualitative")
        
    assert result.status == "failed"
    assert "unexpected error" in result.error
    assert result.data_quality == "unavailable"

# ---------------------------------------------------------
# Test: run_pipeline (End-to-End)
# ---------------------------------------------------------

@pytest.mark.asyncio
@patch("src.agents.orchestrator.pipeline.AGENT_REGISTRY")
@patch("src.agents.orchestrator.pipeline.run_synthesizer")
async def test_run_pipeline_success(mock_run_synthesizer, mock_registry):
    """Test the full pipeline dynamic gather and state update."""
    
    # Create fake Agent class
    class FakeAgent:
        def __init__(self, sub_agents=None):
            self.sub_agents = sub_agents
        
        async def execute(self, state):
            return {"metric": "100"}
            
    mock_registry.get.return_value = MagicMock(
        agent_class=FakeAgent,
        sub_agents={}
    )
    mock_registry.keys.return_value = ["quantitative"]
    
    # Setup mock synthesizer
    async def fake_synthesizer(state):
        state.agent_statuses["synthesizer"] = "success"
        state.final_thesis = "Synthesized!"
        return state
        
    mock_run_synthesizer.side_effect = fake_synthesizer
    
    state = SharedState(
        user_query="test",
        ticker="TCS.NS",
        company_name="Tata",
        industry="IT",
        sector="Tech",
        currency="INR",
        execution_plan=ExecutionPlan(
            response_type="dashboard",
            agents={
                "quantitative": AgentExecution(
                    should_run=True,
                    sub_agents=[]
                )
            }
        )
    )
    
    with patch("src.agents.orchestrator.pipeline.get_agent_names", return_value=["quantitative"]):
        with patch("src.agents.orchestrator.pipeline.get_sub_agent_names", return_value=[]):
            final_state = await run_pipeline(state)
            
    assert final_state.agent_statuses["quantitative"] == "success"
    assert final_state.quantitative_result.data == {"metric": "100"}
    assert final_state.agent_statuses["synthesizer"] == "success"
    assert final_state.final_thesis == "Synthesized!"
