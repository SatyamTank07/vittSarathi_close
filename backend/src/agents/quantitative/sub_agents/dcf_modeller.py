import logging
from src.agents.base.base_agent import BaseAgent
from src.agents.base.shared_state import SharedState, AgentResult

logger = logging.getLogger("vittsarathi.agents.quantitative.dcf_modeller")

class DCFModellerAgent(BaseAgent):

    agent_name = "dcf_modeller"

    async def execute(self, state: SharedState) -> AgentResult:
        """
        Stub implementation. Performs DCF valuation projection.
        Full implementation: Task DCF-001.
        """
        logger.info(f"[dcf_modeller] Running for {state.ticker} (stub)")

        # Stub returns a minimal successful result
        # Replace this block with real logic when implementing
        return AgentResult(
            data={"stub": True, "agent": "dcf_modeller", "ticker": state.ticker},
            status="success",
            data_quality="low",
            fallback_used=False,
            agent_name="dcf_modeller"
        )
