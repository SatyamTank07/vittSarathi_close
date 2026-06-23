import json
import logging
from datetime import datetime, timedelta, timezone
import requests
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

@tool
def fetch_exchange_announcements(ticker: str, days_to_lookback: int = 30) -> dict:
    """
    Fetches recent corporate announcements from NSE and BSE for a given ticker.
    Returns structured announcement data with titles, dates, and source exchange.

    Args:
        ticker (str): Stock ticker e.g. HDFCBANK.NS or HDFCBANK.BO
        days_to_lookback (int): How many days back to look

    Returns:
        dict: { "announcements": list[dict], "fetched_at": str, "source": str }
    """
    try:
        # Strip the .NS or .BO suffix to get the bare symbol (e.g. HDFCBANK)
        symbol = ticker.split(".")[0]
        
        # BSE feed requires numeric scrip code lookup — add BSECode resolver in future.
        # BSE API structure for reference:
        # https://api.bseindia.com/BseIndiaAPI/api/AnnGetAnnouncementss/w?strScrip={bse_code}&strType=C&iPageNo=1&iPageSize=20
        
        # Attempt NSE only for now
        url = f"https://www.nseindia.com/api/top-corp-info?symbol={symbol}&market=equities"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9",
        }
        
        session = requests.Session()
        # NSE often requires visiting the homepage first to obtain necessary cookies
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if isinstance(data, dict):
            items = data.get("announcements", data.get("data", []))
        elif isinstance(data, list):
            items = data
        else:
            items = []
            
        announcements = []
        cutoff_date = datetime.now() - timedelta(days=days_to_lookback)
        
        for item in items:
            title = item.get("desc", "")
            an_dt = item.get("an_dt", "")
            
            announcement = {
                "title": title,
                "date": an_dt,
                "exchange": "NSE"
            }
            
            # Filter results to days_to_lookback using the an_dt date field.
            if an_dt:
                try:
                    parsed_date = None
                    for fmt in (
                        "%d-%b-%Y %H:%M:%S",
                        "%d-%b-%Y",
                        "%Y-%m-%d %H:%M:%S",
                        "%Y-%m-%d",
                        "%d-%m-%Y %H:%M:%S",
                        "%d-%m-%Y"
                    ):
                        try:
                            parsed_date = datetime.strptime(an_dt.strip(), fmt)
                            break
                        except ValueError:
                            continue
                            
                    # If parsing succeeded, apply the days_to_lookback filter
                    if parsed_date and parsed_date < cutoff_date:
                        continue
                except Exception:
                    # If date parsing fails on any item, include it anyway with "date": item["an_dt"] unparsed
                    pass
            
            announcements.append(announcement)
            
        return {
            "announcements": announcements,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "NSE",
            "ticker": ticker
        }
        
    except Exception as e:
        logger.warning(f"Failed to fetch exchange announcements for {ticker}: {e}")
        return {
            "announcements": [],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "NSE",
            "ticker": ticker,
            "error": str(e)
        }
