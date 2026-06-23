import asyncio
import json
from src.tools.screener_scraper import scrape_screener

async def main():
    ticker = "RELIANCE"
    print(f"Starting scraper for {ticker}...")
    
    result = await scrape_screener(ticker)
    
    print("\n=== Scraper Result ===")
    print(f"Data Source: {result.data_source}")
    print(f"Error: {result.error}")
    
    if result.ratios:
        print("\n--- Ratios ---")
        print(json.dumps(result.ratios, indent=2))
        
    if result.financials:
        print("\n--- Financials Extracted ---")
        for key in result.financials.keys():
            print(f"- {key}")

if __name__ == "__main__":
    asyncio.run(main())
