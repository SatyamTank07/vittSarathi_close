import pytest
from unittest.mock import patch
from src.mcp.fmp_server import calc_valuation_ratios
from src.mcp.risk_and_governance import fetch_insider_disclosures

def test_fmp_valuation_success():
    """Scenario 1: FMP API Success Path"""
    # Note: Requires valid FMP_API_KEY in .env
    result = calc_valuation_ratios(ticker="AAPL", period="annual", limit=1)
    
    # If API key is missing or invalid, the tool returns {"error": "..."}
    assert "error" not in result, f"FMP Tool returned an error. Is your FMP_API_KEY valid? Error: {result.get('error')}"
    
    assert "ticker" in result, "Expected 'ticker' in response."
    assert result["ticker"] == "AAPL"
    assert "ratios" in result, "Expected 'ratios' in response."
    assert isinstance(result["ratios"], list)
    
    if len(result["ratios"]) > 0:
        assert "priceEarningsRatio" in result["ratios"][0], "Expected 'priceEarningsRatio' metric in the ratio object."

def test_fmp_invalid_ticker():
    """Scenario 2: FMP API Graceful Failure"""
    result = calc_valuation_ratios(ticker="FAKE_TICKER_999", period="annual", limit=1)
    
    # It should not throw a raw python exception, but return a safe error dict
    assert "error" in result, "Expected an error message dictionary for a fake ticker, but got success."

def test_risk_insider_disclosures():
    """Scenario 3: Risk & Governance Success"""
    result = fetch_insider_disclosures(ticker="RELIANCE", days=90, transaction_type="All")
    
    assert "error" not in result, f"Risk Tool returned an error: {result.get('error')}"
    assert result["ticker"] == "RELIANCE", "Data mismatch on ticker."
    assert "insider_disclosures" in result, "Missing insider_disclosures data block."
    assert "source" in result["insider_disclosures"], "Missing data source identifier."

@patch("src.mcp.risk_and_governance.pnsea", None)
def test_risk_fallback_mechanism():
    """Scenario 4: Risk & Governance Fallback Logic"""
    # We use unittest.mock.patch to pretend the 'pnsea' module is missing.
    # This forces _fetch_with_fallback to cleanly transition to 'bseindia'.
    
    result = fetch_insider_disclosures(ticker="TCS", days=90, transaction_type="All")
    
    assert "error" not in result, f"Fallback failed, returned error dict: {result.get('error')}"
    assert "insider_disclosures" in result
    
    # Assert the source specifically identifies as bseindia
    source = result["insider_disclosures"].get("source")
    assert source == "bseindia", f"Expected fallback source to be 'bseindia', but got '{source}'"
