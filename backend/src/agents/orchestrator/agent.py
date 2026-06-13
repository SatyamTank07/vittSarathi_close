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

    async def execute(self, state: SharedState = None, user_query: str = None) -> SharedState:
        if not user_query:
            raise ValueError("Orchestrator requires a user_query.")

        logger.info(f"[{self.agent_name}] Starting analysis for query: {user_query}")

        user_prompt = (
            f"Analyze the following User Query: '{user_query}'\n\n"
            f"1. Extract the company name and use the get_company_profile tool to fetch its profile.\n"
            f"2. Produce the structured task allocation JSON. Set should_run = true ONLY for agents needed to answer the query.\n"
            f"3. Assign a `confidence_score` between 0.0 and 1.0 to your entity extraction. If the user query is ambiguous (e.g., 'Tata' could mean Tata Motors, Tata Steel, or TCS), set the `confidence_score` below 0.8 and populate `disambiguation_candidates` with 2-3 likely options."
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
            user_query=user_query,
            ticker=meta.ticker,
            company_name=meta.company_name,
            industry=meta.industry,
            sector=meta.sector,
            currency="INR" if ".NS" in meta.ticker or ".BO" in meta.ticker else "USD",
            summary="",
            routing_framework=meta.routing_framework,
            task_allocations=task_allocations,
            clarification_needed=meta.confidence_score < 0.8,
        )
        state.agent_statuses[self.agent_name] = "completed"

        logger.info(f"[{self.agent_name}] SharedState created for {state.ticker}")
        return state


orchestrator = OrchestratorAgent()
