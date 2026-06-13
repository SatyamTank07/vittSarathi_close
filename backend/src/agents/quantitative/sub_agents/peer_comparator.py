import logging
from src.agents.base.base_agent import BaseAgent
from src.agents.base.shared_state import SharedState, AgentResult

logger = logging.getLogger("vittsarathi.agents.quantitative.peer_comparator")

class PeerComparatorAgent(BaseAgent):

    agent_name = "peer_comparator"

    async def execute(self, state: SharedState) -> AgentResult:
        """
        Stub implementation. Fetches peer ratios for comparison.
        Full implementation: Task PEER-001.
        """
        logger.info(f"[peer_comparator] Running for {state.ticker} (stub)")

        return AgentResult(
            data={"stub": True, "agent": "peer_comparator", "ticker": state.ticker},
            status="success",
            data_quality="low",
            fallback_used=False,
            agent_name="peer_comparator"
        )
