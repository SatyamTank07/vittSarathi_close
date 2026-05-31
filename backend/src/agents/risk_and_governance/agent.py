import logging
from src.agents.base.base_agent import BaseAgent
from src.agents.base.shared_state import SharedState, RiskGovernanceOutput
from src.tools.analyze_risk_governance_tool import analyze_risk_governance
from .config import RiskGovernanceConfig

logger = logging.getLogger("vittsarathi.agents.risk")

class RiskGovernanceAgent(BaseAgent):
    def __init__(self):
        self.config = RiskGovernanceConfig
        self.agent_name = self.config["name"]
        self.model = self.config["model"]
        self.max_tokens = self.config.get("max_tokens", 700)
        self.system_prompt = self.config["system_prompt"]

    def _build_prompt(self, state: SharedState) -> str:
        data = state.stock_data

        # ── Build dynamic instructions from task_allocations (preferred) or fallback ──
        if state.task_allocations and state.task_allocations.agent_4_risk_governance:
            alloc = state.task_allocations.agent_4_risk_governance
            risk_lines = "\n".join(f"  - {r}" for r in alloc.risk_vectors_to_score)
            instructions = (
                f"RISK VECTORS TO SCORE:\n{risk_lines}\n\n"
                f"COMPLIANCE BENCHMARKS: {alloc.compliance_benchmarks}"
            )
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
            
        state.risk_governance = structured

        state.agent_statuses[self.agent_name] = "completed"
        logger.info(f"[{self.agent_name}] Done for {state.ticker}")
        return state

risk_agent = RiskGovernanceAgent()
