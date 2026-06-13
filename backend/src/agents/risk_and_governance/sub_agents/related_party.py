import logging
from src.agents.base.base_agent import BaseAgent
from src.agents.base.shared_state import SharedState, AgentResult

logger = logging.getLogger("vittsarathi.agents.risk_and_governance.related_party")

class RelatedPartyAgent(BaseAgent):

    agent_name = "related_party"

    async def execute(self, state: SharedState) -> AgentResult:
        """
        Stub implementation. Analyses RPTs.
        Full implementation: Task RPT-001.
        """
        logger.info(f"[related_party] Running for {state.ticker} (stub)")

        return AgentResult(
            data={"stub": True, "agent": "related_party", "ticker": state.ticker},
            status="success",
            data_quality="low",
            fallback_used=False,
            agent_name="related_party"
        )
