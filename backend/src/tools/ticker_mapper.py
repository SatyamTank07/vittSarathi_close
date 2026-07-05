"""
Utility to map standard exchange tickers (e.g., Yahoo Finance tickers) to the internal database company_id format.
"""
import difflib
from sqlalchemy import text
from src.core.database.connection import SessionLocal

def get_available_company_ids() -> list[str]:
    """Fetches all distinct company IDs currently loaded in the database."""
    try:
        with SessionLocal() as db:
            result = db.execute(text("SELECT DISTINCT company_id FROM rag_documents"))
            return [row[0] for row in result]
    except Exception as e:
        print(f"Error fetching company IDs: {e}")
        return []

def normalize_company_id(ticker: str) -> str:
    """
    Dynamically converts a stock ticker (e.g. 'BAJFINANCE.NS') to the closest matching 
    internal DB company_id (e.g. 'BAJAJ_FINANCE') using fuzzy string matching.
    """
    if not ticker:
        return ticker
        
    try:
        available_ids = get_available_company_ids()
        if not available_ids:
            return ticker
            
        # Exact match check
        if ticker in available_ids:
            return ticker
        if ticker.upper() in available_ids:
            return ticker.upper()
            
        # Clean the input ticker (remove suffixes like .NS, .BO)
        ticker_clean = ticker.lower().replace(".ns", "").replace(".bo", "").strip()
        
        # Fuzzy match against database IDs
        db_ids_lower = [cid.lower() for cid in available_ids]
        matches = difflib.get_close_matches(ticker_clean, db_ids_lower, n=1, cutoff=0.3)
        
        if matches:
            matched_lower = matches[0]
            # Return the original casing found in the database
            for original_id in available_ids:
                if original_id.lower() == matched_lower:
                    return original_id
                    
    except Exception as e:
        print(f"Error during ticker normalization: {e}")
        
    return ticker
