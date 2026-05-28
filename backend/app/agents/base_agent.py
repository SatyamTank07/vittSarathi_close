"""
Base Agent — Abstract base class for all VittSarathi agents.

Provides:
- LLM factory with model selection (gpt-4o-mini vs gpt-3.5-turbo)
- max_tokens=700 enforced on all calls
- Structured JSON parsing from LLM responses
- Retry logic (1 retry on failure)
- Logging
"""

import os
import json
import logging
from abc import ABC, abstractmethod
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.agents.shared_state import SharedState

logger = logging.getLogger("vittsarathi.agents")


class BaseAgent(ABC):
    """Abstract base class for all agents in the orchestration pipeline."""

    # Subclasses set these
    agent_name: str = "base"
    model: str = "gpt-3.5-turbo"  # Override to "gpt-4o-mini" for orchestrator/synthesizer
    max_tokens: int = 700

    def _get_llm(self) -> ChatOpenAI:
        """Create an LLM instance with the agent's model and token settings."""
        api_key = os.environ.get("OPENAI_API_KEY", "")
        api_key = api_key.strip('"').strip("'")

        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set in the environment variables.")

        return ChatOpenAI(
            model=self.model,
            temperature=0.4,
            max_tokens=self.max_tokens,
            api_key=api_key,
        )

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """
        Call the LLM with retry logic.
        Returns the raw text content from the model.
        """
        llm = self._get_llm()
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        last_error = None
        for attempt in range(2):  # 1 retry
            try:
                logger.info(f"[{self.agent_name}] Calling {self.model} (attempt {attempt + 1})")
                response = llm.invoke(messages)
                logger.info(f"[{self.agent_name}] Got response ({len(response.content)} chars)")
                return response.content
            except Exception as e:
                last_error = e
                logger.warning(f"[{self.agent_name}] Attempt {attempt + 1} failed: {e}")

        raise RuntimeError(f"[{self.agent_name}] All retries exhausted: {last_error}")

    def _parse_json(self, text: str) -> dict:
        """
        Extract JSON from an LLM response.
        Handles responses wrapped in ```json ... ``` code blocks.
        """
        cleaned = text.strip()

        # Strip markdown code fences if present
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # Remove first line (```json) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"[{self.agent_name}] Failed to parse JSON: {e}\nRaw text:\n{text[:500]}")
            # Return a fallback with the raw text
            return {"_raw_text": text, "_parse_error": str(e)}

    @abstractmethod
    async def execute(self, state: SharedState) -> SharedState:
        """
        Execute the agent's logic.
        
        Args:
            state: The shared state to read from and write to.
            
        Returns:
            The updated shared state.
        """
        ...
