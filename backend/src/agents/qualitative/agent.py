import logging
import asyncio
from typing import Dict, Type
from src.agents.base.base_agent import BaseAgent
from src.agents.base.shared_state import SharedState, QualitativeOutput
from src.tools.search_narrative_disclosures_tool import search_narrative_disclosures
from src.tools.historical_trend_search_tool import historical_trend_search
from .config import QualitativeConfig

logger = logging.getLogger("vittsarathi.agents.qualitative")

class QualitativeAgent(BaseAgent):
    def __init__(self, sub_agents: Dict[str, Type[BaseAgent]] = None):
        self.config = QualitativeConfig
        self.agent_name = self.config["name"]
        self.model = self.config["model"]
        self.max_tokens = self.config.get("max_tokens", 700)
        self.system_prompt = self.config["system_prompt"]
        self.approved_sub_agents: Dict[str, Type[BaseAgent]] = sub_agents or {}

    def _build_prompt(self, state: SharedState) -> str:
        data = state.stock_data

        focus_list = []
        if (
            state.execution_plan
            and "qualitative" in state.execution_plan.agents
        ):
            focus_list = state.execution_plan.agents["qualitative"].focus

        if focus_list:
            focus_lines = "\n".join(f"  - {m}" for m in focus_list)
            instructions = f"FOCUS METRICS:\n{focus_lines}"
        else:
            instructions = state.industry_instructions.get("qualitative_focus", "")

        context = {
            "Company": state.company_name,
            "Ticker": state.ticker,
            "Sector": state.sector,
            "Industry": state.industry,
            "Business Summary": state.summary[:500] if state.summary else "Not available",
            "Market Cap": data.get("marketCap"),
            "Revenue": data.get("totalRevenue"),
            "Revenue Growth": data.get("revenueGrowth"),
            "Profit Margins": data.get("profitMargins"),
            "ROE": data.get("returnOnEquity"),
            "Insider Holding %": data.get("heldPercentInsiders"),
            "Institutional Holding %": data.get("heldPercentInstitutions"),
            "Recommendation": data.get("recommendationKey"),
            "Target Price": data.get("targetMeanPrice"),
            "Number of Analysts": data.get("numberOfAnalystOpinions"),
            "Full Time Employees": data.get("fullTimeEmployees"),
        }

        context_str = "\n".join(f"  {k}: {v}" for k, v in context.items() if v is not None)

        return f"""Analyze the following company:

{context_str}

INDUSTRY-SPECIFIC FOCUS:
{instructions}

Produce your qualitative business assessment as a JSON object."""

    async def execute(self, state: SharedState) -> SharedState:
        from langchain.agents import create_agent

        state.agent_statuses[self.agent_name] = "running"
        logger.info(f"[{self.agent_name}] Analyzing {state.ticker}")

        prompt = self._build_prompt(state)

        agent = create_agent(
            model=self._get_llm(),
            tools=[search_narrative_disclosures, historical_trend_search],
            system_prompt=self.system_prompt,
            response_format=QualitativeOutput
        )

        result = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]})
        
        structured: QualitativeOutput = result.get("structured_response")
        
        if not structured:
            raise ValueError(f"[{self.agent_name}] Agent did not return a structured_response for '{state.ticker}'")
            
        from src.agents.base.shared_state import AgentResult
        state.qualitative_result = AgentResult(
            data=structured,
            status="success",
            data_quality="high",
            fallback_used=False,
            agent_name=self.agent_name
        )

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

qualitative_agent = QualitativeAgent()
