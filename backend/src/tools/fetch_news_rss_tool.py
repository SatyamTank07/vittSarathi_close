import httpx
import xml.etree.ElementTree as ET
import urllib.parse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from langchain_core.tools import tool

@tool
def fetch_news_rss(ticker: str, company_name: str, days_to_lookback: int = 30) -> list[str]:
    """
    Fetches the latest news headlines from Google News RSS for a given company.
    Filters the headlines to only include those from the last `days_to_lookback` days.
    
    Args:
        ticker (str): The stock ticker of the company (e.g., RELIANCE.NS)
        company_name (str): The name of the company to search for
        days_to_lookback (int): The number of days to look back for news
        
    Returns:
        list[str]: A list of news headlines
    """
    query = urllib.parse.quote_plus(company_name)
    url = f"https://news.google.com/rss/search?q={query}"
    
    try:
        response = httpx.get(url, follow_redirects=True, timeout=10.0)
        response.raise_for_status()
        root = ET.fromstring(response.text)
    except Exception as e:
        return [f"Error fetching news for {company_name}: {str(e)}"]

    headlines = []
    now = datetime.now(timezone.utc)
    
    for item in root.findall('.//item'):
        title = item.find('title')
        pubDate = item.find('pubDate')
        
        if title is not None and title.text:
            headline = title.text.strip()
            
            if pubDate is not None and pubDate.text:
                try:
                    dt = parsedate_to_datetime(pubDate.text)
                    if (now - dt).days <= days_to_lookback:
                        headlines.append(headline)
                    else:
                        break  # Early exit if chronologically sorted
                except Exception:
                    # If date parsing fails, include it by default
                    headlines.append(headline)
            else:
                headlines.append(headline)
                
    return headlines
