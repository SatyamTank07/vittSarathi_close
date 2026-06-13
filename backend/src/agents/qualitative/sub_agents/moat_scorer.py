import logging
from src.agents.base.base_agent import BaseAgent
from src.agents.base.shared_state import SharedState, AgentResult

logger = logging.getLogger("vittsarathi.agents.qualitative.moat_scorer")

class MoatScorerAgent(BaseAgent):

    agent_name = "moat_scorer"

    async def execute(self, state: SharedState) -> AgentResult:
        """
        Stub implementation. Scores competitive moat.
        Full implementation: Task MOAT-001.
        """
        logger.info(f"[moat_scorer] Running for {state.ticker} (stub)")

        return AgentResult(
            data={"stub": True, "agent": "moat_scorer", "ticker": state.ticker},
            status="success",
            data_quality="low",
            fallback_used=False,
            agent_name="moat_scorer"
        )
