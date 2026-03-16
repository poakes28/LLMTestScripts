#!/usr/bin/env python3
"""
CLI Runner: Data Collector

Fetches prices, fundamentals, and syncs portfolios.
Designed to be called by Windows Task Scheduler 3x daily.

Usage:
    python scripts/collect.py                  # Full price pull
    python scripts/collect.py --fundamentals   # Fetch fundamentals
    python scripts/collect.py --sync           # Sync Schwab portfolio
    python scripts/collect.py --historical     # Fetch full history
"""

import sys
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils import setup_logging
from src.collector.price_fetcher import PriceFetcher
from src.collector.schwab_client import SchwabClient
from src.collector.paper_portfolio import PaperPortfolioManager
from loguru import logger


def main():
    parser = argparse.ArgumentParser(description="Trading System Data Collector")
    parser.add_argument("--fundamentals", action="store_true",
                        help="Fetch fundamental data (slower)")
    parser.add_argument("--sync", action="store_true",
                        help="Sync real portfolio from Schwab")
    parser.add_argument("--historical", action="store_true",
                        help="Fetch full historical price data")
    parser.add_argument("--update-paper", action="store_true",
                        help="Update paper portfolio prices and record daily values")
    args = parser.parse_args()

    setup_logging("collector")
    logger.info("=" * 60)
    logger.info("DATA COLLECTOR STARTING")
    logger.info("=" * 60)

    fetcher = PriceFetcher()

    try:
        if args.historical:
            logger.info("Fetching full historical data...")
            historical = fetcher.fetch_historical_prices(period="2y")
            if not historical.empty:
                fetcher.save_prices(historical, "daily")
                logger.info(f"Saved {len(historical)} historical records")

        elif args.fundamentals:
            fetcher.run_fundamentals_pull()

        elif args.sync:
            schwab = SchwabClient()
            if schwab.is_configured:
                schwab.sync_real_portfolio()
            else:
                logger.warning("Schwab not configured. Skipping sync.")

        else:
            # Default: price pull
            fetcher.run_price_pull()

        # Always update paper portfolios if prices changed
        if args.update_paper or not (args.fundamentals or args.sync):
            try:
                prices_df = fetcher.fetch_current_prices()
                if not prices_df.empty:
                    price_map = dict(zip(prices_df["ticker"], prices_df["close"]))
                    mgr = PaperPortfolioManager()
                    mgr.update_all_prices(price_map)
                    mgr.record_all_daily_values()
                    logger.info("Paper portfolios updated")
            except Exception as e:
                logger.warning(f"Paper portfolio update failed: {e}")

        logger.info("Data collection complete")

    except Exception as e:
        logger.error(f"Collection failed: {e}")
        raise


if __name__ == "__main__":
    main()
