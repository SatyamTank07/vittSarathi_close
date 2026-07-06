import httpx
from datetime import datetime, timezone
from langchain_core.tools import tool

# Mapping our standard indicator names to World Bank API codes
WB_INDICATORS = {
    "gdp_growth": "NY.GDP.MKTP.KD.ZG",      # keep — annual GDP, World Bank
    "inflation_wb": "FP.CPI.TOTL.ZG"         # rename key, keep as fallback
}

DBIE_INDICATORS = {
    "repo_rate": "BSR1:RBIINTR.M",
    "inflation": "BSR1:INFL.M"
}

def get_wb_data(country_code: str, indicator_code: str) -> dict:
    url = f"http://api.worldbank.org/v2/country/{country_code}/indicator/{indicator_code}?format=json&per_page=5"
    try:
        response = httpx.get(url, timeout=10.0, follow_redirects=True)
        response.raise_for_status()
        data = response.json()
        
        if len(data) > 1 and isinstance(data[1], list):
            # The API returns the data sorted by date descending (newest first)
            # Filter out null values
            valid_data = [item for item in data[1] if item.get("value") is not None]
            
            if len(valid_data) >= 1:
                current_value = valid_data[0]["value"]
                
                trend = "Stable"
                if len(valid_data) >= 2:
                    prev_value = valid_data[1]["value"]
                    if current_value > prev_value + 0.1:
                        trend = "Increasing"
                    elif current_value < prev_value - 0.1:
                        trend = "Decreasing"
                
                return {
                    "current_value": round(current_value, 2),
                    "unit": "%",
                    "trend": trend,
                    "period": valid_data[0]["date"],
                    "source": "World Bank",
                    "fetched_at": datetime.now(timezone.utc).isoformat()
                }
    except Exception as e:
        return {"error": f"Failed to fetch data: {str(e)}", "fetched_at": datetime.now(timezone.utc).isoformat()}
        
    return {"error": "No valid data found", "fetched_at": datetime.now(timezone.utc).isoformat()}

def get_rbi_dbie_data(series_id: str) -> dict:
    url = f"https://dbie.rbi.org.in/DBIE/dbie.rbi?site=api"
    try:
        # DBIE frequently has SSL cert mismatch issues, so we set verify=False
        response = httpx.get(url, params={"seriesId": series_id}, timeout=10.0, follow_redirects=True, verify=False)
        
        import logging
        logging.info(f"DBIE fetch for {series_id} returned status {response.status_code}")
        logging.info(f"DBIE response (first 200 chars): {response.text[:200]}")
        
        response.raise_for_status()
        try:
            data_json = response.json()
        except ValueError:
            raise ValueError("RBI API endpoint is broken and returned HTML instead of JSON data.")
            
        valid_data = [item for item in data_json.get("data", []) if item[1] is not None]
        
        if len(valid_data) >= 1:
            current_value = valid_data[0][1]
            period = valid_data[0][0]
            
            trend = "Stable"
            if len(valid_data) >= 2:
                prev_value = valid_data[1][1]
                if current_value > prev_value + 0.1:
                    trend = "Increasing"
                elif current_value < prev_value - 0.1:
                    trend = "Decreasing"
                    
            return {
                "current_value": round(current_value, 2),
                "unit": "%",
                "trend": trend,
                "period": period,
                "source": "RBI DBIE",
                "fetched_at": datetime.now(timezone.utc).isoformat()
            }
        else:
            raise ValueError("No valid data found in DBIE response")
    except Exception as e:
        return {
            "error": str(e),
            "source": "RBI DBIE",
            "fetched_at": datetime.now(timezone.utc).isoformat()
        }

def get_rbi_homepage_repo_rate() -> dict:
    url = "https://www.rbi.org.in/"
    try:
        from bs4 import BeautifulSoup
        import re
        response = httpx.get(url, timeout=10.0, verify=False, follow_redirects=True)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        rate_val = None
        for tr in soup.find_all('tr'):
            if 'Policy Repo Rate' in tr.text:
                text = tr.text.replace('\n', '').replace('\r', '').strip()
                match = re.search(r'([\d\.]+)\s*%', text)
                if match:
                    rate_val = float(match.group(1))
                    break
                    
        if rate_val is not None:
            return {
                "current_value": rate_val,
                "unit": "%",
                "trend": "Stable", 
                "period": datetime.now(timezone.utc).strftime("%Y-%m"),
                "source": "RBI Homepage",
                "fetched_at": datetime.now(timezone.utc).isoformat()
            }
        else:
            return {"error": "Could not parse Repo Rate from RBI homepage", "fetched_at": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        return {"error": str(e), "source": "RBI Homepage", "fetched_at": datetime.now(timezone.utc).isoformat()}

@tool
def fetch_macro_indicators(country_code: str, indicators_needed: list[str]) -> dict:
    """
    Fetches the specified macroeconomic indicators for a given country.
    
    Args:
        country_code (str): The ISO 2-letter country code (e.g., 'IN' for India)
        indicators_needed (list[str]): A list of requested indicators. 
                                       Supported values: 'gdp_growth', 'inflation', 'repo_rate', 'inflation_wb'
                                       
    Returns:
        dict: A structured payload with current values, trends, and sources.
    """
    result = {
        "country": country_code,
        "macro_data": {}
    }
    
    for indicator in indicators_needed:
        if indicator == "repo_rate":
            if country_code == "IN":
                # For India, we have a highly accurate live scraper
                data = get_rbi_homepage_repo_rate()
            else:
                # For other countries, use World Bank Lending Interest Rate as a global proxy
                data = get_wb_data(country_code, "FR.INR.LEND")
            result["macro_data"][indicator] = data
            
        elif indicator == "inflation" or indicator == "inflation_wb":
            # World Bank Consumer Price Index (CPI) is globally standardized
            data = get_wb_data(country_code, "FP.CPI.TOTL.ZG")
            result["macro_data"][indicator] = data
            
        elif indicator == "gdp_growth":
            # World Bank Annual GDP Growth is globally standardized
            data = get_wb_data(country_code, "NY.GDP.MKTP.KD.ZG")
            result["macro_data"][indicator] = data
            
        else:
            result["macro_data"][indicator] = {
                "error": "Unsupported indicator requested",
                "fetched_at": datetime.now(timezone.utc).isoformat()
            }
            
    return result
