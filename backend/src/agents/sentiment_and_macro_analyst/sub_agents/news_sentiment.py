import logging
from src.agents.base.base_agent import BaseAgent
from src.agents.base.shared_state import SharedState, AgentResult

logger = logging.getLogger("vittsarathi.agents.sentiment.news_sentiment")

class NewsSentimentAgent(BaseAgent):

    agent_name = "news_sentiment"

    async def execute(self, state: SharedState) -> AgentResult:
        """
        Stub implementation. FinBERT NLP on headlines.
        Full implementation: Task NEWS-001.
        """
        logger.info(f"[news_sentiment] Running for {state.ticker} (stub)")

        return AgentResult(
            data={"stub": True, "agent": "news_sentiment", "ticker": state.ticker},
            status="success",
            data_quality="low",
            fallback_used=False,
            agent_name="news_sentiment"
        )
