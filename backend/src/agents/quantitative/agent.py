import logging
import asyncio
from typing import Dict, Type
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.client import MultiServerMCPClient
from src.agents.base.base_agent import BaseAgent
from src.agents.base.shared_state import SharedState, QuantitativeOutput
from src.tools.fetch_financial_statements_tool import fetch_financial_statements
from src.tools.deep_dive_cross_ref_tool import deep_dive_cross_ref
from src.tools.historical_trend_search_tool import historical_trend_search
from src.tools.screener_scraper import scrape_screener, DataSource
from .config import QuantitativeConfig

logger = logging.getLogger("vittsarathi.agents.quantitative")

class QuantitativeAgent(BaseAgent):
    def __init__(self, sub_agents: Dict[str, Type[BaseAgent]] = None):
        self.config = QuantitativeConfig
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
            and "quantitative" in state.execution_plan.agents
        ):
            focus_list = state.execution_plan.agents["quantitative"].focus

        if focus_list:
            focus_lines = "\n".join(f"  - {m}" for m in focus_list)
            instructions = f"FOCUS METRICS:\n{focus_lines}"
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

        # ── NEW: append screener data if available ──
        screener_block = ""
        screener_ratios = data.get("screener_ratios", {})
        screener_financials = data.get("screener_financials", {})
        screener_source = data.get("screener_data_source", "not_attempted")

        if screener_ratios:
            ratios_str = "\n".join(f"  {k}: {v}" for k, v in screener_ratios.items())
            screener_block += f"\nSCREENER.IN LIVE RATIOS (source: {screener_source}):\n{ratios_str}"

        if screener_financials:
            for table_name, table_data in screener_financials.items():
                if table_data is not None:
                    screener_block += f"\nSCREENER.IN {table_name.upper().replace('_', ' ')}:\n"
                    years = table_data.get("years", [])
                    rows = table_data.get("rows", {})
                    if years:
                        screener_block += f"  Years: {', '.join(years)}\n"
                    for row_label, row_values in rows.items():
                        screener_block += f"  {row_label}: {', '.join(str(v) for v in row_values)}\n"

        if screener_source == "failed":
            screener_block = "\nSCREENER.IN DATA: unavailable — use yfinance data above only.\n"

        return f"""Analyze the following stock data:

{metrics_str}
{screener_block}

INDUSTRY-SPECIFIC FOCUS:
{instructions}

Produce your quantitative analysis as a JSON object."""

    async def execute(self, state: SharedState) -> SharedState:
        from langchain.agents import create_agent
        from src.agents.base.shared_state import AgentResult

        state.agent_statuses[self.agent_name] = "running"
        logger.info(f"[{self.agent_name}] Analyzing {state.ticker}")

        # ── Step A: Scrape Screener.in first, inject into state.stock_data ──
        try:
            screener_result = await scrape_screener(state.ticker)

            state.stock_data["screener_ratios"]      = screener_result.ratios
            state.stock_data["screener_financials"]  = screener_result.financials
            state.stock_data["screener_data_source"] = screener_result.data_source.value

            if screener_result.data_source == DataSource.FAILED:
                logger.warning(
                    f"[{self.agent_name}] Screener scrape failed for {state.ticker}: "
                    f"{screener_result.error} — continuing with yfinance data only"
                )
            else:
                logger.info(
                    f"[{self.agent_name}] Screener data loaded — "
                    f"source: {screener_result.data_source.value}, "
                    f"ratios: {list(screener_result.ratios.keys())}"
                )

        except Exception as e:
            # Never let scraper failure crash the agent
            logger.error(
                f"[{self.agent_name}] Screener scraper raised unexpected exception "
                f"for {state.ticker}: {e}",
                exc_info=True
            )
            state.stock_data["screener_data_source"] = DataSource.FAILED.value
            state.stock_data["screener_ratios"]      = {}
            state.stock_data["screener_financials"]  = {}

        # ── Step B: Build prompt — now includes screener data ──
        prompt = self._build_prompt(state)

        # ── Step C: FMP MCP + RAG agent — unchanged from before ──
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

                result = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]})

        # ── Step D: Extract result — unchanged from before ──
        structured: QuantitativeOutput = result.get("structured_response")

        if not structured:
            raise ValueError(
                f"[{self.agent_name}] Agent did not return a structured_response "
                f"for '{state.ticker}'"
            )

        state.quantitative_result = AgentResult(
            data=structured,
            status="success",
            data_quality="high",
            fallback_used=False,
            agent_name=self.agent_name
        )

        state.agent_statuses[self.agent_name] = "completed"
        logger.info(f"[{self.agent_name}] Main analysis done for {state.ticker}")

        # ── Step E: Sub-agents — unchanged from before ──
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

quantitative_agent = QuantitativeAgent()
