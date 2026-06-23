import httpx
import xml.etree.ElementTree as ET
import urllib.parse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from langchain_core.tools import tool

@tool
def read_custom_rss(url: str, days_to_lookback: int = 30) -> list[dict]:
    """
    Reads a custom RSS feed from the given URL and returns the headlines/titles.
    Filters the items to only include those from the last `days_to_lookback` days.
    
    Args:
        url (str): The URL of the RSS feed
        days_to_lookback (int): The number of days to look back for news
        
    Returns:
        list[dict]: A list of news items containing headline, source, and published_at
    """
    try:
        response = httpx.get(url, follow_redirects=True, timeout=10.0)
        response.raise_for_status()
        root = ET.fromstring(response.text)
    except Exception as e:
        return [{"headline": f"Error reading RSS feed from {url}: {str(e)}", "source": "Unknown", "published_at": None}]

    try:
        source_domain = urllib.parse.urlparse(url).netloc
    except Exception:
        source_domain = "Unknown"

    headlines = []
    now = datetime.now(timezone.utc)
    
    for item in root.findall('.//item'):
        title = item.find('title')
        pubDate = item.find('pubDate')
        
        if title is not None and title.text:
            headline_text = title.text.strip()
            published_at_str = None
            
            if pubDate is not None and pubDate.text:
                try:
                    dt = parsedate_to_datetime(pubDate.text)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if (now - dt).days <= days_to_lookback:
                        dt_utc = dt.astimezone(timezone.utc)
                        published_at_str = dt_utc.isoformat()
                    else:
                        break  # Early exit if chronologically sorted
                except Exception:
                    pass  # If date parsing fails, include it by default with published_at=None
            
            headlines.append({
                "headline": headline_text,
                "source": source_domain,
                "published_at": published_at_str
            })
                
    return headlines
