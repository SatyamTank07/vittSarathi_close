import httpx
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from langchain_core.tools import tool

@tool
def read_custom_rss(url: str, days_to_lookback: int = 30) -> list[str]:
    """
    Reads a custom RSS feed from the given URL and returns the headlines/titles.
    Filters the items to only include those from the last `days_to_lookback` days.
    
    Args:
        url (str): The URL of the RSS feed
        days_to_lookback (int): The number of days to look back for news
        
    Returns:
        list[str]: A list of news headlines/titles from the RSS feed
    """
    try:
        response = httpx.get(url, follow_redirects=True, timeout=10.0)
        response.raise_for_status()
        root = ET.fromstring(response.text)
    except Exception as e:
        return [f"Error reading RSS feed from {url}: {str(e)}"]

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
