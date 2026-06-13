import logging
from src.agents.base.base_agent import BaseAgent
from src.agents.base.shared_state import SharedState, AgentResult

logger = logging.getLogger("vittsarathi.agents.sentiment.fii_dii_tracker")

class FIIDIITrackerAgent(BaseAgent):

    agent_name = "fii_dii_tracker"

    async def execute(self, state: SharedState) -> AgentResult:
        """
        Stub implementation. Tracks FII/DII data.
        Full implementation: Task FIIDII-001.
        """
        logger.info(f"[fii_dii_tracker] Running for {state.ticker} (stub)")

        return AgentResult(
            data={"stub": True, "agent": "fii_dii_tracker", "ticker": state.ticker},
            status="success",
            data_quality="low",
            fallback_used=False,
            agent_name="fii_dii_tracker"
        )
