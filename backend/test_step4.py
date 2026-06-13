import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from src.agents.base.shared_state import OrchestratorOutputV2, OrchestrationMeta, ExecutionPlan, AgentExecution, ResponseType

def test_orchestrator_output_model():
    # Confirm the new model parses correctly
    output = OrchestratorOutputV2(
        orchestration_meta=OrchestrationMeta(
            ticker="HDFCBANK.NS",
            company_name="HDFC Bank Ltd.",
            sector="Financial Services",
            industry="Banks - Regional",
            routing_framework="Banking",
            confidence_score=0.95,
            disambiguation_candidates=[],
        ),
        execution_plan=ExecutionPlan(
            response_type=ResponseType.DASHBOARD,
            overall_reasoning="Full analysis requested.",
            agents={
                "quantitative":    AgentExecution(should_run=True,  focus=["NIM", "NPA"], reasoning="Ratio query"),
                "qualitative":     AgentExecution(should_run=True,  focus=["Moat"], reasoning="Strategy context needed"),
                "risk_governance": AgentExecution(should_run=True,  focus=["Promoter pledge"], reasoning="Risk check"),
                "sentiment":       AgentExecution(should_run=False, reasoning="Not needed for this query"),
            }
        )
    )

    assert output.execution_plan.response_type == ResponseType.DASHBOARD
    assert output.execution_plan.agents["quantitative"].should_run == True
    assert output.execution_plan.agents["sentiment"].should_run == False
    assert output.orchestration_meta.confidence_score == 0.95
    assert "NIM" in output.execution_plan.agents["quantitative"].focus

    print("Step 4 model validation: PASSED")

def test_system_prompt_has_registry():
    from src.agents.orchestrator.config import ORCHESTRATOR_SYSTEM_PROMPT
    # Registry menu must be rendered into the prompt
    assert "quantitative" in ORCHESTRATOR_SYSTEM_PROMPT
    assert "dcf_modeller" in ORCHESTRATOR_SYSTEM_PROMPT
    assert "litigation_scanner" in ORCHESTRATOR_SYSTEM_PROMPT
    assert "{{ agent_registry_menu }}" not in ORCHESTRATOR_SYSTEM_PROMPT  # template tag must be gone
    print("Step 4 prompt injection: PASSED")

if __name__ == "__main__":
    test_orchestrator_output_model()
    test_system_prompt_has_registry()
