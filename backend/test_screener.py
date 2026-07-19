"""
Live integration test for the Screener.in scraper.

Calls scrape_screener() against the real website and dumps the
result to screener_debug.md for manual inspection.

Usage:
    docker exec -i vittsarathi_backend python test_screener.py
"""

import asyncio
import json
import sys
import os
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from src.tools.screener_scraper import scrape_screener


async def test_scraper():
    ticker = os.environ.get("TEST_TICKER", "BAJFINANCE.NS")
    print(f"Testing scraper for {ticker}...")
    start = datetime.now()

    result = await scrape_screener(ticker)

    elapsed = (datetime.now() - start).total_seconds()
    print(f"Done in {elapsed:.1f}s — status: {result.data_source.value}")

    # Write results to markdown
    log_file = "screener_debug.md"
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"# Screener Scraper Debug — {ticker}\n\n")
        f.write(f"- **Timestamp:** {datetime.now().isoformat()}\n")
        f.write(f"- **Elapsed:** {elapsed:.1f}s\n")
        f.write(f"- **Data Source:** `{result.data_source.value}`\n")
        f.write(f"- **Error:** `{result.error}`\n\n")

        f.write("## Top Ratios\n\n")
        if result.ratios:
            for k, v in result.ratios.items():
                f.write(f"- **{k}:** {v}\n")
        else:
            f.write("_No ratios extracted._\n")

        f.write("\n## Financials\n\n")
        if result.financials:
            for table_name, table_data in result.financials.items():
                f.write(f"### {table_name.replace('_', ' ').title()}\n\n")
                if table_data:
                    periods = table_data.get("periods", [])
                    rows = table_data.get("rows", {})
                    f.write(f"**Periods:** {', '.join(str(p) for p in periods)}\n\n")
                    for label, values in rows.items():
                        f.write(f"- **{label}:** {', '.join(str(v) for v in values)}\n")
                else:
                    f.write("_Not available for this company._\n")
                f.write("\n")
        else:
            f.write("_No financials extracted._\n")

        f.write("## Quarterly Results\n\n")
        if result.quarters:
            periods = result.quarters.get("periods", [])
            rows = result.quarters.get("rows", {})
            f.write(f"**Periods:** {', '.join(str(p) for p in periods)}\n\n")
            for label, values in rows.items():
                f.write(f"- **{label}:** {', '.join(str(v) for v in values)}\n")
        else:
            f.write("_No quarterly data extracted._\n")

        f.write("\n## Ratio Trends (Historical)\n\n")
        if result.ratios_history:
            periods = result.ratios_history.get("periods", [])
            rows = result.ratios_history.get("rows", {})
            f.write(f"**Periods:** {', '.join(str(p) for p in periods)}\n\n")
            for label, values in rows.items():
                f.write(f"- **{label}:** {', '.join(str(v) for v in values)}\n")
        else:
            f.write("_No ratio history extracted._\n")

        f.write("\n---\n\n")
        f.write("## Raw JSON\n\n```json\n")
        raw = {
            "ratios": result.ratios,
            "financials": result.financials,
            "quarters": result.quarters,
            "ratios_history": result.ratios_history,
            "data_source": result.data_source.value,
            "error": result.error,
        }
        f.write(json.dumps(raw, indent=2, default=str))
        f.write("\n```\n")

    print(f"Results written to {log_file}")

    # Quick summary to terminal
    if result.ratios:
        print(f"  Ratios: {len(result.ratios)} items")
    tables = sum(1 for v in result.financials.values() if v)
    print(f"  Financial tables: {tables}/3")
    print(f"  Quarters: {'yes' if result.quarters else 'no'}")
    print(f"  Ratio history: {'yes' if result.ratios_history else 'no'}")

    if result.error:
        print(f"  ERROR: {result.error}")
        return 1
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(test_scraper())
    sys.exit(exit_code)
