import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from src.api.main import app

client = TestClient(app)

@pytest.fixture
def mock_yf_info():
    return {
        "symbol": "AAPL",
        "longName": "Apple Inc.",
        "currency": "USD",
        "currentPrice": 150.0,
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "marketCap": 2500000000000,
        "trailingPE": 28.5
    }

def test_get_stock_data_success(mock_yf_info):
    """Test standard ticker fetch."""
    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_instance.info = mock_yf_info
        mock_ticker.return_value = mock_instance
        
        response = client.get("/api/stock/AAPL")
        
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "AAPL"
        assert data["longName"] == "Apple Inc."
        assert data["currentPrice"] == 150.0
        assert data["marketCap"] == 2500000000000

def test_get_stock_data_indian_fallback(mock_yf_info):
    """Test fallback to .NS or .BO for Indian stocks."""
    with patch("yfinance.Ticker") as mock_ticker:
        # First call (TCS) fails/returns empty, second call (TCS.NS) succeeds
        def side_effect(ticker_name):
            mock_inst = MagicMock()
            if ticker_name == "TCS":
                mock_inst.info = {}
            elif ticker_name == "TCS.NS":
                info_copy = mock_yf_info.copy()
                info_copy["symbol"] = "TCS.NS"
                info_copy["longName"] = "Tata Consultancy Services"
                mock_inst.info = info_copy
            return mock_inst
            
        mock_ticker.side_effect = side_effect
        
        response = client.get("/api/stock/TCS")
        
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "TCS.NS"
        assert data["longName"] == "Tata Consultancy Services"

def test_get_stock_data_not_found():
    """Test 404 response for unknown stock."""
    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_instance.info = {}
        mock_ticker.return_value = mock_instance
        
        response = client.get("/api/stock/UNKNOWN")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

@patch("src.api.routes.stock_routes.run_analysis")
@patch("src.api.routes.stock_routes.save_report_to_db")
def test_analyze_stock_success(mock_save_report, mock_run_analysis):
    """Test the POST /api/analyze endpoint successfully triggers the pipeline."""
    # Since run_analysis is an async function being mocked, we must configure it as an AsyncMock 
    # if it's awaited, or just let patch handle it if Python >= 3.8. 
    # Let's ensure it's an AsyncMock to be safe, since it's `await run_analysis()`.
    pass

@pytest.mark.asyncio
@patch("src.api.routes.stock_routes.run_analysis")
@patch("src.api.routes.stock_routes.save_report_to_db")
async def test_analyze_stock_success_async(mock_save_report, mock_run_analysis):
    """Test the POST /api/analyze endpoint successfully triggers the pipeline."""
    from unittest.mock import AsyncMock
    mock_run_analysis_async = AsyncMock()
    mock_run_analysis_async.return_value = {
        "final_thesis": "Good stock",
        "investment_verdict": "Buy",
        "confidence_level": "High"
    }
    mock_run_analysis.side_effect = mock_run_analysis_async
    mock_save_report.return_value = "report-123"
    
    response = client.post("/api/analyze", json={"query": "Analyze AAPL"})
    
    assert response.status_code == 200
    data = response.json()
    assert data["final_thesis"] == "Good stock"
    assert data["investment_verdict"] == "Buy"
    assert data["report_id"] == "report-123"
    
    mock_run_analysis_async.assert_called_once_with("Analyze AAPL")

@patch("src.api.routes.stock_routes.run_analysis")
def test_analyze_stock_value_error(mock_run_analysis):
    """Test 404 response on ValueError during analysis."""
    from unittest.mock import AsyncMock
    mock_run_analysis_async = AsyncMock(side_effect=ValueError("Invalid ticker format."))
    mock_run_analysis.side_effect = mock_run_analysis_async
    
    response = client.post("/api/analyze", json={"query": "Analyze BAD"})
    
    assert response.status_code == 404
    assert response.json()["detail"] == "Invalid ticker format."

@patch("src.api.routes.stock_routes.run_analysis")
def test_analyze_stock_server_error(mock_run_analysis):
    """Test 500 response on unexpected exception."""
    from unittest.mock import AsyncMock
    mock_run_analysis_async = AsyncMock(side_effect=Exception("System crash."))
    mock_run_analysis.side_effect = mock_run_analysis_async
    
    response = client.post("/api/analyze", json={"query": "Analyze AAPL"})
    
    assert response.status_code == 500
    assert "Analysis failed" in response.json()["detail"]
