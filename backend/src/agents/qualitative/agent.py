import logging
from src.agents.base.base_agent import BaseAgent
from src.agents.base.shared_state import SharedState, QualitativeOutput
from src.tools.search_narrative_disclosures_tool import search_narrative_disclosures
from src.tools.historical_trend_search_tool import historical_trend_search
from .config import QualitativeConfig

logger = logging.getLogger("vittsarathi.agents.qualitative")

class QualitativeAgent(BaseAgent):
    def __init__(self):
        self.config = QualitativeConfig
        self.agent_name = self.config["name"]
        self.model = self.config["model"]
        self.max_tokens = self.config.get("max_tokens", 700)
        self.system_prompt = self.config["system_prompt"]

    def _build_prompt(self, state: SharedState) -> str:
        data = state.stock_data

        # ── Build dynamic instructions from task_allocations (preferred) or fallback ──
        if state.task_allocations and state.task_allocations.agent_3_qualitative:
            alloc = state.task_allocations.agent_3_qualitative
            topic_lines = "\n".join(f"  - {t}" for t in alloc.rag_target_topics)
            instructions = (
                f"RAG TARGET TOPICS:\n{topic_lines}\n\n"
                f"COMPETITIVE MOAT CRITERIA: {alloc.competitive_moat_criteria}"
            )
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

        result = agent.invoke({"messages": [{"role": "user", "content": prompt}]})
        
        structured: QualitativeOutput = result.get("structured_response")
        
        if not structured:
            raise ValueError(f"[{self.agent_name}] Agent did not return a structured_response for '{state.ticker}'")
            
        state.qualitative = structured

        state.agent_statuses[self.agent_name] = "completed"
        logger.info(f"[{self.agent_name}] Done for {state.ticker}")
        return state

qualitative_agent = QualitativeAgent()
