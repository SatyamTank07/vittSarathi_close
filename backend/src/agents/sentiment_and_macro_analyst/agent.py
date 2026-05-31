import logging
from src.agents.base.base_agent import BaseAgent
from src.agents.base.shared_state import SharedState, SentimentOutput
from src.tools.fetch_news_rss_tool import fetch_news_rss
from src.tools.read_custom_rss_tool import read_custom_rss
from src.tools.fetch_macro_indicators_tool import fetch_macro_indicators
from .config import SentimentAndMacroConfig

logger = logging.getLogger("vittsarathi.agents.sentiment_and_macro_analyst")

class SentimentAndMacroAgent(BaseAgent):
    def __init__(self):
        self.config = SentimentAndMacroConfig
        self.agent_name = self.config["name"]
        self.model = self.config["model"]
        self.max_tokens = self.config.get("max_tokens", 1000)
        self.system_prompt = self.config["system_prompt"]

    def _build_prompt(self, state: SharedState) -> str:
        # Dynamic instructions from task allocations if available
        if state.task_allocations and hasattr(state.task_allocations, "agent_5_sentiment") and state.task_allocations.agent_5_sentiment:
            alloc = state.task_allocations.agent_5_sentiment
            themes = "\n".join(f"  - {t}" for t in alloc.macro_themes)
            instructions = (
                f"MACRO THEMES TO INVESTIGATE:\n{themes}\n\n"
                f"NEWS FOCUS: {alloc.news_focus}"
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
        tools = [fetch_news_rss, read_custom_rss, fetch_macro_indicators]

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
            
            state.sentiment = structured
        except Exception as e:
            logger.error(f"[{self.agent_name}] Error during execution: {e}")
            raise

        state.agent_statuses[self.agent_name] = "completed"
        logger.info(f"[{self.agent_name}] Done for {state.ticker}")
        return state

sentiment_and_macro_agent = SentimentAndMacroAgent()
