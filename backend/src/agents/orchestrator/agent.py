import logging
from typing import Dict, Any

from langchain.agents import create_agent

from src.agents.base.base_agent import BaseAgent
from src.agents.base.shared_state import SharedState, OrchestratorOutput
from .config import OrchestratorConfig

logger = logging.getLogger("vittsarathi.agents.orchestrator")


class OrchestratorAgent(BaseAgent):
    def __init__(self):
        self.config = OrchestratorConfig
        self.agent_name = self.config["name"]
        self.model = self.config["model"]
        self.max_tokens = self.config.get("max_tokens", 1500)
        self.system_prompt = self.config["system_prompt"]
        self.tools = self.config.get("tools", [])

    async def execute(self, state: SharedState = None, ticker: str = None) -> SharedState:
        if not ticker:
            raise ValueError("Orchestrator requires a ticker symbol.")

        logger.info(f"[{self.agent_name}] Starting analysis for {ticker}")

        user_prompt = (
            f"Perform a fundamental analysis triage for the ticker: {ticker}\n\n"
            f"Use the get_company_profile tool to fetch the company's profile, "
            f"then produce the structured task allocation JSON based on the sector mapping logic."
        )

        # Create the LangChain agent with our tools and desired structured output
        agent = create_agent(
            model=self._get_llm(),
            tools=self.tools,
            system_prompt=self.system_prompt,
            response_format=OrchestratorOutput
        )

        # Invoke the agent using the standard messages payload
        result = agent.invoke({"messages": [{"role": "user", "content": user_prompt}]})
        
        # Extract the structured response (which is fully validated by Pydantic)
        structured: OrchestratorOutput = result.get("structured_response")
        
        if not structured:
            raise ValueError(f"[{self.agent_name}] Agent did not return a structured_response for '{ticker}'")

        meta = structured.orchestration_meta
        task_allocations = structured.task_allocations

        logger.info(
            f"[{self.agent_name}] {meta.company_name} routed via '{meta.routing_framework}' "
            f"(sector={meta.sector}, industry={meta.industry})"
        )

        state = SharedState(
            ticker=meta.ticker,
            company_name=meta.company_name,
            industry=meta.industry,
            sector=meta.sector,
            currency="INR" if ".NS" in meta.ticker or ".BO" in meta.ticker else "USD",
            summary="",
            routing_framework=meta.routing_framework,
            task_allocations=task_allocations,
        )
        state.agent_statuses[self.agent_name] = "completed"

        logger.info(f"[{self.agent_name}] SharedState created for {state.ticker}")
        return state


orchestrator = OrchestratorAgent()
