import pytest
from unittest.mock import patch, MagicMock
import httpx

from src.tools.get_company_profile_tool import get_company_profile
from src.tools.fetch_macro_indicators_tool import fetch_macro_indicators
from src.tools.fetch_news_rss_tool import fetch_news_rss

# ---------------------------------------------------------
# Test: get_company_profile
# ---------------------------------------------------------

@patch("src.tools.get_company_profile_tool.yf.Ticker")
def test_get_company_profile_success(mock_ticker_class):
    """Test successful retrieval of company profile."""
    # Setup mock
    mock_ticker_instance = MagicMock()
    mock_ticker_instance.info = {
        "symbol": "TCS",
        "longName": "Tata Consultancy Services",
        "sector": "Technology",
        "industry": "IT Services",
        "country": "India",
        "exchange": "NSE",
        "currency": "INR",
        "currentPrice": 4000.0,
        "longBusinessSummary": "TCS is an IT services provider."
    }
    mock_ticker_class.return_value = mock_ticker_instance

    # Execute
    result = get_company_profile.invoke({"ticker": "TCS.NS"})

    # Assert
    assert result["ticker"] == "TCS"
    assert result["company_name"] == "Tata Consultancy Services"
    assert result["sector"] == "Technology"
    assert result["current_price"] == 4000.0

@patch("src.tools.get_company_profile_tool.yf.Ticker")
def test_get_company_profile_fallback(mock_ticker_class):
    """Test fallback logic when primary ticker fails or is missing marketCap."""
    # First call (no suffix) returns empty info
    mock_instance_1 = MagicMock()
    mock_instance_1.info = {}
    
    # Second call (with .NS suffix) returns valid info
    mock_instance_2 = MagicMock()
    mock_instance_2.info = {
        "symbol": "RELIANCE.NS",
        "longName": "Reliance Industries",
        "marketCap": 20000000000000, # Triggers the success condition
        "currentPrice": 3000.0
    }
    
    # Configure side effect to return instances in order
    mock_ticker_class.side_effect = [mock_instance_1, mock_instance_2]

    result = get_company_profile.invoke({"ticker": "RELIANCE"})

    assert result["ticker"] == "RELIANCE.NS"
    assert result["company_name"] == "Reliance Industries"
    assert result["current_price"] == 3000.0

# ---------------------------------------------------------
# Test: fetch_macro_indicators
# ---------------------------------------------------------

@patch("src.tools.fetch_macro_indicators_tool.httpx.get")
def test_fetch_macro_indicators_success(mock_get):
    """Test calculating trends correctly from World Bank mock data."""
    # Setup mock httpx response
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    
    # The world bank API returns [pagination_info, [data_list]]
    # Data is returned newest first.
    mock_response.json.return_value = [
        {"page": 1, "pages": 1, "per_page": 5, "total": 2},
        [
            {"date": "2023", "value": 7.5}, # Current
            {"date": "2022", "value": 6.0}  # Previous
        ]
    ]
    mock_get.return_value = mock_response

    # Execute
    result = fetch_macro_indicators.invoke({
        "country_code": "IN", 
        "indicators_needed": ["gdp_growth", "interest_rate"]
    })

    # Assert
    assert result["country"] == "IN"
    
    gdp_data = result["macro_data"]["gdp_growth"]
    assert gdp_data["current_value"] == 7.5
    assert gdp_data["unit"] == "%"
    # Trend should be "Increasing" because 7.5 > 6.0 + 0.1
    assert gdp_data["trend"] == "Increasing"
    
    # Verify interest_rate hardcoded fallback
    ir_data = result["macro_data"]["interest_rate"]
    assert ir_data["source"] == "Not Integrated (Skipped DBIE)"

@patch("src.tools.fetch_macro_indicators_tool.httpx.get")
def test_fetch_macro_indicators_error(mock_get):
    """Test error handling when API fails."""
    mock_get.side_effect = httpx.RequestError("Network Error")
    
    result = fetch_macro_indicators.invoke({
        "country_code": "IN", 
        "indicators_needed": ["inflation"]
    })
    
    assert "error" in result["macro_data"]["inflation"]

# ---------------------------------------------------------
# Test: fetch_news_rss
# ---------------------------------------------------------

@patch("src.tools.fetch_news_rss_tool.httpx.get")
def test_fetch_news_rss_success(mock_get):
    """Test parsing XML and filtering by date."""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    
    # Create fake XML with one recent news item and one old one
    # Note: We must use a valid RFC-2822 date format for parsedate_to_datetime
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    recent_date = (now - timedelta(days=2)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    old_date = (now - timedelta(days=40)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    
    fake_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>News</title>
        <item>
          <title>TCS signs billion dollar deal</title>
          <pubDate>{recent_date}</pubDate>
        </item>
        <item>
          <title>TCS Q1 results announced</title>
          <pubDate>{old_date}</pubDate>
        </item>
      </channel>
    </rss>
    '''
    mock_response.text = fake_xml
    mock_get.return_value = mock_response

    # Execute
    result = fetch_news_rss.invoke({
        "ticker": "TCS.NS", 
        "company_name": "Tata Consultancy Services",
        "days_to_lookback": 30
    })

    # Assert
    # Should only return the recent article
    assert len(result) == 1
    assert "TCS signs billion dollar deal" in result[0]

@patch("src.tools.fetch_news_rss_tool.httpx.get")
def test_fetch_news_rss_error(mock_get):
    """Test error handling when HTTP request fails."""
    mock_get.side_effect = httpx.HTTPStatusError(
        "404 Not Found", request=MagicMock(), response=MagicMock()
    )
    
    result = fetch_news_rss.invoke({
        "ticker": "TCS", 
        "company_name": "Tata Consultancy Services"
    })
    
    assert len(result) == 1
    assert "Error fetching news" in result[0]
