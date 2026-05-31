import logging
import asyncio
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.client import MultiServerMCPClient
from src.agents.base.base_agent import BaseAgent
from src.agents.base.shared_state import SharedState, QuantitativeOutput
from src.tools.fetch_financial_statements_tool import fetch_financial_statements
from src.tools.deep_dive_cross_ref_tool import deep_dive_cross_ref
from src.tools.historical_trend_search_tool import historical_trend_search
from .config import QuantitativeConfig

logger = logging.getLogger("vittsarathi.agents.quantitative")

class QuantitativeAgent(BaseAgent):
    def __init__(self):
        self.config = QuantitativeConfig
        self.agent_name = self.config["name"]
        self.model = self.config["model"]
        self.max_tokens = self.config.get("max_tokens", 700)
        self.system_prompt = self.config["system_prompt"]

    def _build_prompt(self, state: SharedState) -> str:
        data = state.stock_data

        # ── Build dynamic instructions from task_allocations (preferred) or fallback ──
        if state.task_allocations and state.task_allocations.agent_2_quantitative:
            alloc = state.task_allocations.agent_2_quantitative
            focus_lines = "\n".join(f"  - {m}" for m in alloc.focus_metrics)
            instructions = (
                f"FOCUS METRICS:\n{focus_lines}\n\n"
                f"VALUATION METHODOLOGY: {alloc.valuation_methodology}\n\n"
                f"HISTORICAL DEPTH: Analyze at least {alloc.historical_depth_years} years of data."
            )
        else:
            instructions = state.industry_instructions.get("quantitative_focus", "")

        metrics = {
            "Company": state.company_name,
            "Ticker": state.ticker,
            "Sector": state.sector,
            "Industry": state.industry,
            "Currency": state.currency,
            "Current Price": state.current_price,
            "Market Cap": data.get("marketCap"),
            "PE Ratio (Trailing)": data.get("trailingPE"),
            "PE Ratio (Forward)": data.get("forwardPE"),
            "PB Ratio": data.get("priceToBook"),
            "PEG Ratio": data.get("pegRatio"),
            "EV/EBITDA": data.get("enterpriseToEbitda"),
            "Revenue": data.get("totalRevenue"),
            "Revenue Growth": data.get("revenueGrowth"),
            "Earnings Growth": data.get("earningsGrowth"),
            "Gross Margins": data.get("grossMargins"),
            "EBITDA Margins": data.get("ebitdaMargins"),
            "Profit Margins": data.get("profitMargins"),
            "Operating Margins": data.get("operatingMargins"),
            "ROE": data.get("returnOnEquity"),
            "ROA": data.get("returnOnAssets"),
            "Debt to Equity": data.get("debtToEquity"),
            "Current Ratio": data.get("currentRatio"),
            "Quick Ratio": data.get("quickRatio"),
            "Total Debt": data.get("totalDebt"),
            "Total Cash": data.get("totalCash"),
            "Free Cash Flow": data.get("freeCashflow"),
            "Operating Cash Flow": data.get("operatingCashflow"),
            "Dividend Yield": data.get("dividendYield"),
            "Payout Ratio": data.get("payoutRatio"),
            "52W High": data.get("fiftyTwoWeekHigh"),
            "52W Low": data.get("fiftyTwoWeekLow"),
            "50D Average": data.get("fiftyDayAverage"),
            "200D Average": data.get("twoHundredDayAverage"),
            "Beta": data.get("beta"),
        }

        metrics_str = "\n".join(f"  {k}: {v}" for k, v in metrics.items() if v is not None)

        return f"""Analyze the following stock data:

{metrics_str}

INDUSTRY-SPECIFIC FOCUS:
{instructions}

Produce your quantitative analysis as a JSON object."""

    async def execute(self, state: SharedState) -> SharedState:
        from langchain.agents import create_agent
        
        state.agent_statuses[self.agent_name] = "running"
        logger.info(f"[{self.agent_name}] Analyzing {state.ticker}")

        prompt = self._build_prompt(state)
        
        # Connect to MCP server via stdio
        server_params = StdioServerParameters(
            command="python",
            args=["src/mcp/fmp_server.py"]
        )
        
        async with stdio_client(server_params) as (read, write):
            async with MultiServerMCPClient() as client:
                await client.connect_to_server("fmp", read=read, write=write)
                mcp_tools = await client.get_tools()
                
                rag_tools = [fetch_financial_statements, deep_dive_cross_ref, historical_trend_search]
                all_tools = mcp_tools + rag_tools
                
                agent = create_agent(
                    model=self._get_llm(),
                    tools=all_tools,
                    system_prompt=self.system_prompt,
                    response_format=QuantitativeOutput
                )
                
                # Using ainvoke to properly support async MCP tools within the active connection
                result = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]})
        
        structured: QuantitativeOutput = result.get("structured_response")
        
        if not structured:
            raise ValueError(f"[{self.agent_name}] Agent did not return a structured_response for '{state.ticker}'")
            
        state.quantitative = structured

        state.agent_statuses[self.agent_name] = "completed"
        logger.info(f"[{self.agent_name}] Done for {state.ticker}")
        return state

quantitative_agent = QuantitativeAgent()
