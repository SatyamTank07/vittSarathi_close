"""
Base Agent — Abstract base class for all VittSarathi agents.
"""

import os
import logging
from abc import ABC, abstractmethod
from langchain_openai import ChatOpenAI

from src.agents.base.shared_state import SharedState

logger = logging.getLogger("vittsarathi.agents")


class BaseAgent(ABC):
    """Abstract base class for all agents in the orchestration pipeline."""

    agent_name: str = "base"
    model: str = "gpt-3.5-turbo"
    max_tokens: int = 1500

    def _get_llm(self) -> ChatOpenAI:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        api_key = api_key.strip('"').strip("'")

        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set in the environment variables.")

        # By returning the ChatOpenAI object, we can pass it directly 
        # to langchain.agents.create_agent
        return ChatOpenAI(
            model=self.model,
            temperature=0.4,
            max_tokens=self.max_tokens,
            api_key=api_key,
        )

    @abstractmethod
    async def execute(self, state: SharedState) -> SharedState:
        ...
