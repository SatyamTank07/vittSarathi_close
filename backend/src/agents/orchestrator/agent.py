# src/agents/orchestrator/agent.py

import logging
from langchain.agents import create_agent

from src.agents.base.base_agent import BaseAgent
from src.agents.base.shared_state import SharedState, OrchestratorOutputV2
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

    async def execute(
        self,
        state: SharedState = None,
        user_query: str = None
    ) -> SharedState:

        if not user_query:
            raise ValueError("Orchestrator requires a user_query.")

        logger.info(f"[{self.agent_name}] Starting for query: {user_query}")

        user_prompt = (
            f"User Query: '{user_query}'\n\n"
            f"1. Extract the company name and use get_company_profile to fetch its profile.\n"
            f"2. Classify the response_type (dashboard / chat / patch).\n"
            f"3. Decide which agents and sub-agents to run based on the query intent.\n"
            f"4. Produce the ExecutionPlan JSON. "
            f"Use only agent and sub-agent names listed in the system prompt. "
            f"Add a reasoning field for every agent explaining your decision."
        )

        agent = create_agent(
            model=self._get_llm(),
            tools=self.tools,
            system_prompt=self.system_prompt,
            response_format=OrchestratorOutputV2      # <-- switched from OrchestratorOutput
        )

        result = agent.invoke({
            "messages": [{"role": "user", "content": user_prompt}]
        })

        structured: OrchestratorOutputV2 = result.get("structured_response")

        if not structured:
            raise ValueError(
                f"[{self.agent_name}] No structured_response returned for query: {user_query}"
            )

        meta = structured.orchestration_meta
        execution_plan = structured.execution_plan

        logger.info(
            f"[{self.agent_name}] {meta.company_name} | "
            f"framework={meta.routing_framework} | "
            f"response_type={execution_plan.response_type} | "
            f"agents_to_run={[k for k,v in execution_plan.agents.items() if v.should_run]}"
        )

        # Log reasoning for each agent decision
        for agent_name, agent_exec in execution_plan.agents.items():
            logger.info(
                f"[{self.agent_name}] {agent_name}: "
                f"should_run={agent_exec.should_run} | "
                f"reasoning={agent_exec.reasoning}"
            )

        # Warn if confidence is low — clarification needed
        clarification_needed = meta.confidence_score < 0.8

        new_state = SharedState(
            user_query=user_query,
            ticker=meta.ticker,
            company_name=meta.company_name,
            industry=meta.industry,
            sector=meta.sector,
            currency="INR" if (
                ".NS" in meta.ticker or ".BO" in meta.ticker
            ) else "USD",
            summary="",
            routing_framework=meta.routing_framework,
            execution_plan=execution_plan,        # <-- switched from task_allocations
            clarification_needed=clarification_needed,
            disambiguation_candidates=meta.disambiguation_candidates,
        )
        new_state.agent_statuses[self.agent_name] = "completed"

        logger.info(
            f"[{self.agent_name}] SharedState created for {new_state.ticker}"
        )
        return new_state


orchestrator = OrchestratorAgent()
