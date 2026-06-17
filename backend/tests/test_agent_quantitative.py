import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from typing import Dict, Type

from src.agents.quantitative.agent import QuantitativeAgent
from src.agents.base.base_agent import BaseAgent
from src.agents.base.shared_state import SharedState, QuantitativeOutput, AgentResult
from src.tools.screener_scraper import ScreenerResult, DataSource

class DummySubAgent(BaseAgent):
    """A dummy sub-agent to test dispatching."""
    agent_name = "dummy_sub"
    async def execute(self, state: SharedState) -> SharedState:
        return AgentResult(
            status="success",
            agent_name="dummy_sub",
            data={"result": "sub_done"},
            data_quality="high",
            fallback_used=False
        )

@pytest.mark.asyncio
@patch("src.agents.quantitative.agent.scrape_screener")
@patch("src.agents.quantitative.agent.stdio_client")
@patch("src.agents.quantitative.agent.MultiServerMCPClient")
@patch("langchain.agents.create_agent")
async def test_quantitative_agent_flow(
    mock_create_agent, 
    mock_mcp_client_cls, 
    mock_stdio_client, 
    mock_scrape_screener
):
    """
    Test the full flow of QuantitativeAgent:
    1. Screener.in scraping
    2. MCP client connection
    3. LLM Agent execution
    4. Sub-agent dispatch
    """
    
    # 1. Mock Scraper
    mock_scrape_screener.return_value = ScreenerResult(
        ticker="TCS.NS",
        ratios={"PE": 25},
        financials={"quarterly": {"years": ["2023"], "rows": {"Sales": [1000]}}},
        data_source=DataSource.SCREENER_SCRAPED,
        error=None
    )
    
    # 2. Mock MCP Stdio Context Manager
    mock_stdio_cm = AsyncMock()
    mock_stdio_cm.__aenter__.return_value = (MagicMock(), MagicMock()) # (read, write)
    mock_stdio_client.return_value = mock_stdio_cm
    
    # 3. Mock MultiServerMCPClient
    mock_client_instance = AsyncMock()
    mock_client_instance.get_tools.return_value = [{"name": "fake_mcp_tool"}]
    
    mock_mcp_client_cm = AsyncMock()
    mock_mcp_client_cm.__aenter__.return_value = mock_client_instance
    mock_mcp_client_cls.return_value = mock_mcp_client_cm
    
    # 4. Mock LangChain Agent
    mock_agent_instance = AsyncMock()
    mock_agent_instance.ainvoke.return_value = {
        "structured_response": QuantitativeOutput(
            industry_framework_used="SaaS",
            analysis_blocks={"Revenue Growth": "High growth"},
            raw_ratios={"PE": 25.0},
            overall_quantitative_health="Solid financials"
        )
    }
    mock_create_agent.return_value = mock_agent_instance
    
    # Run Agent
    sub_agents_dict: Dict[str, Type[BaseAgent]] = {"dummy_sub": DummySubAgent}
    agent = QuantitativeAgent(sub_agents=sub_agents_dict)
    
    # Mock OPENAI_API_KEY for BaseModel _get_llm
    with patch.dict("os.environ", {"OPENAI_API_KEY": "fake_key"}):
        state = SharedState(
            user_query="Analyze TCS",
            ticker="TCS.NS",
            company_name="Tata Consultancy Services",
            industry="IT",
            sector="Tech",
            currency="INR"
        )
        
        result_state = await agent.execute(state)
        
        # Verify Screener Injection
        assert result_state.stock_data["screener_data_source"] == "screener_scraped"
        assert result_state.stock_data["screener_ratios"]["PE"] == 25
        
        # Verify MCP Calls
        mock_client_instance.connect_to_server.assert_called_once()
        mock_client_instance.get_tools.assert_called_once()
        
        # Verify LangChain Agent Tools Merged
        # It should pass MCP tools + RAG tools to create_agent
        call_kwargs = mock_create_agent.call_args.kwargs
        passed_tools = call_kwargs["tools"]
        assert len(passed_tools) == 4 # 1 MCP + 3 RAG tools (fetch_financial_statements, deep_dive_cross_ref, historical_trend_search)
        
        # Verify Output
        assert result_state.quantitative_result.status == "success"
        assert result_state.quantitative_result.data.overall_quantitative_health == "Solid financials"
        
        # Verify Sub-Agents
        assert "quantitative.dummy_sub" in result_state.sub_agent_results
        assert result_state.sub_agent_results["quantitative.dummy_sub"].status == "success"
