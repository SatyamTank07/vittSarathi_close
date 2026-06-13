import logging
import asyncio
from typing import Dict, Type
from src.agents.base.base_agent import BaseAgent
from src.agents.base.shared_state import SharedState, RiskGovernanceOutput
from src.tools.analyze_risk_governance_tool import analyze_risk_governance
from .config import RiskGovernanceConfig

logger = logging.getLogger("vittsarathi.agents.risk")

class RiskGovernanceAgent(BaseAgent):
    def __init__(self, sub_agents: Dict[str, Type[BaseAgent]] = None):
        self.config = RiskGovernanceConfig
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
            and "risk_governance" in state.execution_plan.agents
        ):
            focus_list = state.execution_plan.agents["risk_governance"].focus

        if focus_list:
            focus_lines = "\n".join(f"  - {m}" for m in focus_list)
            instructions = f"FOCUS METRICS:\n{focus_lines}"
        else:
            instructions = state.industry_instructions.get("risk_focus", "")

        risk_data = {
            "Company": state.company_name,
            "Ticker": state.ticker,
            "Sector": state.sector,
            "Industry": state.industry,
            "Current Price": state.current_price,
            "Market Cap": data.get("marketCap"),
            "PE Ratio (Trailing)": data.get("trailingPE"),
            "PE Ratio (Forward)": data.get("forwardPE"),
            "PB Ratio": data.get("priceToBook"),
            "Debt to Equity": data.get("debtToEquity"),
            "Current Ratio": data.get("currentRatio"),
            "Quick Ratio": data.get("quickRatio"),
            "Total Debt": data.get("totalDebt"),
            "Total Cash": data.get("totalCash"),
            "Free Cash Flow": data.get("freeCashflow"),
            "Insider Holding %": data.get("heldPercentInsiders"),
            "Institutional Holding %": data.get("heldPercentInstitutions"),
            "Beta": data.get("beta"),
            "52W High": data.get("fiftyTwoWeekHigh"),
            "52W Low": data.get("fiftyTwoWeekLow"),
            "Audit Risk": data.get("auditRisk"),
            "Board Risk": data.get("boardRisk"),
            "Compensation Risk": data.get("compensationRisk"),
            "Shareholder Rights Risk": data.get("shareHolderRightsRisk"),
            "Overall Risk": data.get("overallRisk"),
            "Recommendation": data.get("recommendationKey"),
            "Short Ratio": data.get("shortRatio"),
            "Short % of Float": data.get("shortPercentOfFloat"),
            "Payout Ratio": data.get("payoutRatio"),
        }

        risk_str = "\n".join(f"  {k}: {v}" for k, v in risk_data.items() if v is not None)

        return f"""Investigate the following company for risks and governance concerns:

{risk_str}

INDUSTRY-SPECIFIC RISK FOCUS:
{instructions}

Produce your risk assessment as a JSON object. Be thorough and skeptical."""

    async def execute(self, state: SharedState) -> SharedState:
        from langchain.agents import create_agent
        from mcp import StdioServerParameters
        from mcp.client.stdio import stdio_client
        from langchain_mcp_adapters.client import MultiServerMCPClient

        state.agent_statuses[self.agent_name] = "running"
        logger.info(f"[{self.agent_name}] Investigating {state.ticker}")

        prompt = self._build_prompt(state)

        server_params = StdioServerParameters(
            command="python",
            args=["src/mcp/risk_and_governance.py"]
        )
        
        async with stdio_client(server_params) as (read, write):
            async with MultiServerMCPClient() as client:
                await client.connect_to_server("risk", read=read, write=write)
                mcp_tools = await client.get_tools()
                
                rag_tools = [analyze_risk_governance]
                all_tools = mcp_tools + rag_tools
                
                agent = create_agent(
                    model=self._get_llm(),
                    tools=all_tools,
                    system_prompt=self.system_prompt,
                    response_format=RiskGovernanceOutput
                )

                result = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]})
        
        structured: RiskGovernanceOutput = result.get("structured_response")
        
        if not structured:
            raise ValueError(f"[{self.agent_name}] Agent did not return a structured_response for '{state.ticker}'")
            
        from src.agents.base.shared_state import AgentResult
        state.risk_governance_result = AgentResult(
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

risk_agent = RiskGovernanceAgent()
