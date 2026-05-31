import httpx
from langchain_core.tools import tool

# Mapping our standard indicator names to World Bank API codes
WB_INDICATORS = {
    "gdp_growth": "NY.GDP.MKTP.KD.ZG",
    "inflation": "FP.CPI.TOTL.ZG"
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
                    "source": "World Bank"
                }
    except Exception as e:
        return {"error": f"Failed to fetch data: {str(e)}"}
        
    return {"error": "No valid data found"}

@tool
def fetch_macro_indicators(country_code: str, indicators_needed: list[str]) -> dict:
    """
    Fetches the specified macroeconomic indicators for a given country.
    
    Args:
        country_code (str): The ISO 2-letter country code (e.g., 'IN' for India)
        indicators_needed (list[str]): A list of requested indicators. 
                                       Supported values: 'gdp_growth', 'inflation', 'interest_rate'
                                       
    Returns:
        dict: A structured payload with current values, trends, and sources.
    """
    result = {
        "country": country_code,
        "macro_data": {}
    }
    
    for indicator in indicators_needed:
        if indicator in WB_INDICATORS:
            wb_code = WB_INDICATORS[indicator]
            data = get_wb_data(country_code, wb_code)
            result["macro_data"][indicator] = data
        elif indicator == "interest_rate":
            # DBIE / RBI integration has been explicitly skipped
            result["macro_data"][indicator] = {
                "current_value": None,
                "unit": "%",
                "trend": "Unknown",
                "source": "Not Integrated (Skipped DBIE)"
            }
        else:
            result["macro_data"][indicator] = {"error": "Unsupported indicator requested"}
            
    return result
