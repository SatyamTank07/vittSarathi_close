import pytest
import json
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from src.tools.screener_scraper import scrape_screener, DataSource, _failure_counts, _circuit_open

# We must reset the global circuit breaker before each test
@pytest.fixture(autouse=True)
def reset_circuit_breaker():
    _failure_counts.clear()
    _circuit_open.clear()

@pytest.mark.asyncio
@patch("src.tools.screener_scraper.MultiServerMCPClient")
@patch("src.tools.screener_scraper.create_react_agent")
@patch.dict('os.environ', {'OPENAI_API_KEY': 'fake_key'})
async def test_scrape_screener_success(mock_create_agent, mock_mcp):
    """Test successful scrape with full data."""

    # Mock MCP Client
    mock_client_instance = AsyncMock()
    mock_client_instance.get_tools.return_value = []
    mock_mcp.return_value = mock_client_instance

    # Mock Agent
    mock_agent_instance = AsyncMock()
    mock_create_agent.return_value = mock_agent_instance

    # Mock LLM Response matching the expected JSON
    fake_json = {
        "ratios": {"Market Cap": "1,000,000", "ROE": "20%"},
        "profit_loss": {"years": ["2023"], "rows": {"Sales": ["100"]}},
        "balance_sheet": {"years": ["2023"], "rows": {"Assets": ["500"]}},
        "cash_flow": {"years": ["2023"], "rows": {"Ops": ["50"]}}
    }
    
    mock_message = MagicMock()
    mock_message.content = f"```json\n{json.dumps(fake_json)}\n```"
    mock_agent_instance.ainvoke.return_value = {"messages": [mock_message]}

    # Execute
    result = await scrape_screener("TCS.NS")

    assert result.ticker == "TCS.NS"
    assert result.data_source == DataSource.SCREENER_SCRAPED
    assert result.error is None
    assert result.ratios["ROE"] == "20%"
    assert result.financials["profit_loss"]["rows"]["Sales"] == ["100"]

@pytest.mark.asyncio
@patch("src.tools.screener_scraper.MultiServerMCPClient")
@patch("src.tools.screener_scraper.create_react_agent")
@patch.dict('os.environ', {'OPENAI_API_KEY': 'fake_key'})
async def test_scrape_screener_partial_data(mock_create_agent, mock_mcp):
    """Test scrape when some tables are missing (should be marked PARTIAL)."""
    mock_client_instance = AsyncMock()
    mock_client_instance.get_tools.return_value = []
    mock_mcp.return_value = mock_client_instance
    mock_agent_instance = AsyncMock()
    mock_create_agent.return_value = mock_agent_instance

    # Mock missing cash flow
    fake_json = {
        "ratios": {"Market Cap": "1,000,000"},
        "profit_loss": {"years": ["2023"], "rows": {"Sales": ["100"]}},
        "balance_sheet": {"years": ["2023"], "rows": {"Assets": ["500"]}},
        "cash_flow": None
    }
    
    mock_message = MagicMock()
    mock_message.content = json.dumps(fake_json)
    mock_agent_instance.ainvoke.return_value = {"messages": [mock_message]}

    result = await scrape_screener("HDFCBANK.NS")

    assert result.data_source == DataSource.PARTIAL
    assert result.financials["cash_flow"] is None

@pytest.mark.asyncio
@patch("src.tools.screener_scraper.MultiServerMCPClient")
@patch("src.tools.screener_scraper.create_react_agent")
@patch.dict('os.environ', {'OPENAI_API_KEY': 'fake_key'})
async def test_scrape_screener_circuit_breaker(mock_create_agent, mock_mcp):
    """Test that 3 failures open the circuit breaker."""
    mock_client_instance = AsyncMock()
    mock_client_instance.get_tools.return_value = []
    mock_mcp.return_value = mock_client_instance
    mock_agent_instance = AsyncMock()
    mock_create_agent.return_value = mock_agent_instance

    # Make the agent raise a TimeoutError to simulate failure
    mock_agent_instance.ainvoke.side_effect = asyncio.TimeoutError()

    # Fail 1
    res1 = await scrape_screener("FAIL1")
    assert res1.data_source == DataSource.FAILED
    
    # Fail 2
    res2 = await scrape_screener("FAIL2")
    assert res2.data_source == DataSource.FAILED

    # Fail 3
    res3 = await scrape_screener("FAIL3")
    assert res3.data_source == DataSource.FAILED

    # The 4th call should not even invoke the agent, it should hit circuit breaker
    mock_agent_instance.ainvoke.reset_mock()
    res4 = await scrape_screener("FAIL4")
    
    assert res4.data_source == DataSource.FAILED
    assert "Circuit breaker open" in res4.error
    mock_agent_instance.ainvoke.assert_not_called()
