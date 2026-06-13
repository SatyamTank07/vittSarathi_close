import logging
from src.agents.base.base_agent import BaseAgent
from src.agents.base.shared_state import SharedState, AgentResult

logger = logging.getLogger("vittsarathi.agents.qualitative.capex_intent")

class CapexIntentAgent(BaseAgent):

    agent_name = "capex_intent"

    async def execute(self, state: SharedState) -> AgentResult:
        """
        Stub implementation. Extracts capex commitments.
        Full implementation: Task CAPEX-001.
        """
        logger.info(f"[capex_intent] Running for {state.ticker} (stub)")

        return AgentResult(
            data={"stub": True, "agent": "capex_intent", "ticker": state.ticker},
            status="success",
            data_quality="low",
            fallback_used=False,
            agent_name="capex_intent"
        )
