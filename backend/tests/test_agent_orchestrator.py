import pytest
from unittest.mock import patch, MagicMock
from src.agents.orchestrator.agent import OrchestratorAgent
from src.agents.base.shared_state import SharedState, OrchestratorOutputV2, OrchestrationMeta, ExecutionPlan, AgentExecution

@pytest.mark.asyncio
@patch("src.agents.orchestrator.agent.create_agent")
async def test_orchestrator_success(mock_create_agent):
    """Test that orchestrator successfully parses intent and routes to correct agents."""
    
    # Setup mock LLM response
    mock_agent_instance = MagicMock()
    
    # Create fake structured output exactly as LangChain would return it
    fake_output = OrchestratorOutputV2(
        orchestration_meta=OrchestrationMeta(
            ticker="TCS.NS",
            company_name="Tata Consultancy Services",
            sector="Technology",
            industry="IT Services",
            routing_framework="multi-agent",
            confidence_score=0.95,
            disambiguation_candidates=[]
        ),
        execution_plan=ExecutionPlan(
            response_type="dashboard",
            agents={
                "quantitative": AgentExecution(
                    should_run=True,
                    reasoning="Need to check financials",
                    sub_agents=["dcf_modeller"],
                    focus=["Revenue growth"]
                )
            }
        )
    )
    
    mock_agent_instance.invoke.return_value = {
        "structured_response": fake_output
    }
    mock_create_agent.return_value = mock_agent_instance
    
    # Execute
    agent = OrchestratorAgent()
    result_state = await agent.execute(user_query="How are TCS financials?")
    
    # Assert
    assert result_state.ticker == "TCS.NS"
    assert result_state.company_name == "Tata Consultancy Services"
    assert result_state.currency == "INR" # Due to .NS
    assert result_state.clarification_needed is False
    assert "quantitative" in result_state.execution_plan.agents
    assert result_state.execution_plan.agents["quantitative"].should_run is True
    assert "dcf_modeller" in result_state.execution_plan.agents["quantitative"].sub_agents
    assert result_state.agent_statuses[agent.agent_name] == "completed"

@pytest.mark.asyncio
@patch("src.agents.orchestrator.agent.create_agent")
async def test_orchestrator_clarification_needed(mock_create_agent):
    """Test that low confidence triggers clarification logic."""
    
    mock_agent_instance = MagicMock()
    
    fake_output = OrchestratorOutputV2(
        orchestration_meta=OrchestrationMeta(
            ticker="",
            company_name="Tata",
            sector="",
            industry="",
            routing_framework="multi-agent",
            confidence_score=0.5, # Low confidence
            disambiguation_candidates=[
                {"ticker": "TCS.NS", "company_name": "Tata Consultancy"},
                {"ticker": "TATAMOTORS.NS", "company_name": "Tata Motors"}
            ]
        ),
        execution_plan=ExecutionPlan(
            response_type="chat",
            agents={}
        )
    )
    
    mock_agent_instance.invoke.return_value = {
        "structured_response": fake_output
    }
    mock_create_agent.return_value = mock_agent_instance
    
    # Execute
    agent = OrchestratorAgent()
    result_state = await agent.execute(user_query="Tell me about Tata")
    
    # Assert
    assert result_state.clarification_needed is True
    assert len(result_state.disambiguation_candidates) == 2
    assert result_state.currency == "USD" # Fallback since no .NS in ticker
