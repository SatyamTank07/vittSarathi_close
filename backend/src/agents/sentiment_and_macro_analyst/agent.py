import logging
import asyncio
from typing import Dict, Type
from src.agents.base.base_agent import BaseAgent
from src.agents.base.shared_state import SharedState, SentimentOutput
from src.tools.fetch_news_rss_tool import fetch_news_rss
from src.tools.read_custom_rss_tool import read_custom_rss
from src.tools.fetch_macro_indicators_tool import fetch_macro_indicators
from src.tools.fetch_exchange_announcements_tool import fetch_exchange_announcements
from .config import SentimentAndMacroConfig

logger = logging.getLogger("vittsarathi.agents.sentiment_and_macro_analyst")

class SentimentAndMacroAgent(BaseAgent):
    def __init__(self, sub_agents: Dict[str, Type[BaseAgent]] = None):
        self.config = SentimentAndMacroConfig
        self.agent_name = self.config["name"]
        self.model = self.config["model"]
        self.max_tokens = self.config.get("max_tokens", 1000)
        self.system_prompt = self.config["system_prompt"]
        self.approved_sub_agents: Dict[str, Type[BaseAgent]] = sub_agents or {}

    def _build_prompt(self, state: SharedState) -> str:
        # Dynamic instructions from execution plan
        focus_list = []
        if (
            state.execution_plan
            and "sentiment" in state.execution_plan.agents
        ):
            focus_list = state.execution_plan.agents["sentiment"].focus

        if focus_list:
            themes = "\n".join(f"  - {t}" for t in focus_list)
            instructions = (
                f"MACRO THEMES TO INVESTIGATE:\n{themes}"
            )
        else:
            instructions = state.industry_instructions.get("sentiment_focus", "Focus on recent news and general macro trends.")

        context = {
            "Company": state.company_name,
            "Ticker": state.ticker,
            "Sector": state.sector,
            "Industry": state.industry,
        }

        context_str = "\n".join(f"  {k}: {v}" for k, v in context.items() if v is not None)

        return f"""Analyze the sentiment and macro environment for the following company:

{context_str}

INDUSTRY-SPECIFIC FOCUS:
{instructions}

Please use your tools to fetch recent news and then produce your assessment as a JSON object.
"""

    async def execute(self, state: SharedState) -> SharedState:
        from langchain.agents import create_tool_calling_agent, AgentExecutor
        from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
        
        state.agent_statuses[self.agent_name] = "running"
        logger.info(f"[{self.agent_name}] Analyzing {state.ticker}")

        prompt_text = self._build_prompt(state)

        # Set up tools
        tools = [fetch_news_rss, read_custom_rss, fetch_macro_indicators, fetch_exchange_announcements]

        # Use LangChain's generic create_tool_calling_agent
        # Alternatively, if there's a custom helper in the project, we should use it.
        # Here we'll stick to a common LangChain pattern with structured output
        llm = self._get_llm()
        
        # We need to bind the tools and the structured output format
        # However, typically tool calling and structured output are mutually exclusive in a single invoke.
        # A common pattern is to let the agent run with tools, and then parse the final output.
        
        # For simplicity and consistency with other agents, we can run a standard tool-calling agent
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            ("user", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        agent = create_tool_calling_agent(llm, tools, prompt)
        agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

        try:
            # We add instructions for the agent to return JSON directly in the final answer
            extended_prompt = prompt_text + "\n\nIMPORTANT: Your final answer MUST be valid JSON matching the SentimentOutput schema."
            result = agent_executor.invoke({"input": extended_prompt})
            output_str = result.get("output", "")
            
            # Use LLM to cleanly parse the string into the Pydantic model if it's not strictly structured
            parser_llm = llm.with_structured_output(SentimentOutput)
            structured = parser_llm.invoke(output_str)
            
            if structured.macroeconomic_environment.fetched_at is None:
                from datetime import datetime, timezone
                structured.macroeconomic_environment.fetched_at = datetime.now(timezone.utc).isoformat()

            from src.agents.base.shared_state import AgentResult
            state.sentiment_result = AgentResult(
                data=structured,
                status="success",
                data_quality="high",
                fallback_used=False,
                agent_name=self.agent_name
            )
        except Exception as e:
            logger.error(f"[{self.agent_name}] Error during execution: {e}")
            raise

        state.agent_statuses[self.agent_name] = "completed"
        logger.info(f"[{self.agent_name}] Main analysis done for {state.ticker}")

        if self.approved_sub_agents:
            await self._run_sub_agents(state)

        return state

    async def _run_sub_agents(self, state: SharedState) -> None:
        from src.agents.base.shared_state import AgentResult
        logger.info(
            f"[{self.agent_name}] Running {len(self.approved_sub_agents)} "
            f"sub-agent(s): {list(self.approved_sub_agents.keys())}"
        )

        async def run_one(sub_name: str, sub_cls: Type[BaseAgent]) -> tuple[str, AgentResult]:
            try:
                instance = sub_cls()
                result = await asyncio.wait_for(instance.execute(state), timeout=45.0)
                logger.info(f"[{self.agent_name}] Sub-agent '{sub_name}' completed")
                return sub_name, result
            except asyncio.TimeoutError:
                logger.warning(f"[{self.agent_name}] Sub-agent '{sub_name}' timed out")
                return sub_name, AgentResult(
                    status="failed", error="timeout", agent_name=sub_name,
                    data_quality="unavailable"
                )
            except Exception as e:
                logger.error(f"[{self.agent_name}] Sub-agent '{sub_name}' failed: {e}")
                return sub_name, AgentResult(
                    status="failed", error=str(e), agent_name=sub_name,
                    data_quality="unavailable"
                )

        tasks = [run_one(name, cls) for name, cls in self.approved_sub_agents.items()]
        results = await asyncio.gather(*tasks)

        for sub_name, agent_result in results:
            namespace_key = f"{self.agent_name}.{sub_name}"
            state.sub_agent_results[namespace_key] = agent_result
            logger.info(
                f"[{self.agent_name}] Stored sub-agent result at "
                f"state.sub_agent_results['{namespace_key}'] "
                f"status={agent_result.status}"
            )

sentiment_and_macro_agent = SentimentAndMacroAgent()
