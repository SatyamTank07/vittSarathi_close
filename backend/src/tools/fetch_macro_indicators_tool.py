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
        response = httpx.get(url, timeout=10.0)
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
        response = httpx.get(url, params={"seriesId": series_id}, timeout=10.0)
        
        import logging
        logging.info(f"DBIE fetch for {series_id} returned status {response.status_code}")
        logging.info(f"DBIE response (first 200 chars): {response.text[:200]}")
        
        response.raise_for_status()
        data_json = response.json()
        
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
        if indicator in ["repo_rate", "inflation"]:
            dbie_code = DBIE_INDICATORS[indicator]
            data = get_rbi_dbie_data(dbie_code)
            result["macro_data"][indicator] = data
        elif indicator == "gdp_growth":
            wb_code = WB_INDICATORS["gdp_growth"]
            data = get_wb_data(country_code, wb_code)
            result["macro_data"][indicator] = data
        elif indicator == "inflation_wb":
            wb_code = WB_INDICATORS["inflation_wb"]
            data = get_wb_data(country_code, wb_code)
            result["macro_data"][indicator] = data
        else:
            result["macro_data"][indicator] = {
                "error": "Unsupported indicator requested",
                "fetched_at": datetime.now(timezone.utc).isoformat()
            }
            
    return result
