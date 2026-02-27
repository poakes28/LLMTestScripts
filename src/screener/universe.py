"""
Russell 3000 Universe Manager.

Downloads the Russell 3000 ticker list from iShares IWV ETF holdings CSV
and caches it locally. Falls back to a curated static list if the download fails.
"""

import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
from loguru import logger

from src.utils import load_config, save_parquet, load_parquet, get_data_dir


IWV_HOLDINGS_URL = (
    "https://www.ishares.com/us/products/239714/IWV/1467271812596.ajax"
    "?fileType=csv&fileName=IWV_holdings&dataType=fund"
)

TICKER_PATTERN = re.compile(r'^[A-Z]{1,5}$')


class UniverseManager:
    """Downloads and caches the Russell 3000 ticker universe."""

    def __init__(self):
        cfg = load_config()
        screener_cfg = cfg.get("screener", {})
        self.cache_days = screener_cfg.get("universe_cache_days", 7)
        self.iwv_url = screener_cfg.get("iwv_holdings_url", IWV_HOLDINGS_URL)
        self._data_category = "screener"
        self._filename = "russell3000_universe"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_universe(self, force_refresh: bool = False) -> List[str]:
        """Return the Russell 3000 ticker list, refreshing cache if stale."""
        df = self._load_cached()

        if df is not None and not force_refresh and not self._is_stale(df):
            tickers = df["ticker"].tolist()
            logger.info(f"Russell 3000 universe loaded from cache: {len(tickers)} tickers")
            return tickers

        logger.info("Downloading Russell 3000 universe (IWV holdings)...")
        records = self._download_iwv_holdings()

        if not records:
            logger.warning("IWV download failed — trying Wikipedia fallback")
            records = self._scrape_wikipedia()

        if not records:
            # Last resort: if we have a stale cache, use it
            if df is not None:
                logger.warning("All downloads failed — using stale cache")
                return df["ticker"].tolist()
            raise RuntimeError("Failed to obtain Russell 3000 universe from any source")

        self._save_universe(records)
        tickers = [r["ticker"] for r in records]
        logger.info(f"Russell 3000 universe saved: {len(tickers)} tickers")
        return tickers

    def get_status(self) -> Dict[str, Any]:
        """Return cache status info."""
        df = self._load_cached()
        if df is None or df.empty:
            return {
                "ticker_count": 0,
                "last_updated": None,
                "source": "none",
                "cache_age_days": None,
                "is_stale": True,
            }

        last_updated_str = df["updated_date"].iloc[0] if "updated_date" in df.columns else None
        cache_age = None
        is_stale = True
        if last_updated_str:
            try:
                last_updated = datetime.fromisoformat(last_updated_str)
                cache_age = (datetime.now() - last_updated).total_seconds() / 86400
                is_stale = cache_age > self.cache_days
            except Exception:
                pass

        return {
            "ticker_count": len(df),
            "last_updated": last_updated_str,
            "source": df["source"].iloc[0] if "source" in df.columns else "unknown",
            "cache_age_days": round(cache_age, 2) if cache_age is not None else None,
            "is_stale": is_stale,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_cached(self) -> Optional[pd.DataFrame]:
        return load_parquet(self._data_category, self._filename)

    def _is_stale(self, df: pd.DataFrame) -> bool:
        if "updated_date" not in df.columns or df.empty:
            return True
        try:
            last = datetime.fromisoformat(df["updated_date"].iloc[0])
            return (datetime.now() - last) > timedelta(days=self.cache_days)
        except Exception:
            return True

    def _download_iwv_holdings(self) -> List[Dict]:
        """
        Fetch iShares IWV ETF holdings CSV.
        The CSV has several header rows of fund metadata before the actual data.
        We detect the data header by looking for a row containing 'Ticker'.
        """
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/csv,application/octet-stream,*/*",
            }
            resp = requests.get(self.iwv_url, headers=headers, timeout=30)
            resp.raise_for_status()

            lines = resp.text.splitlines()

            # Find the header row (contains "Ticker" as a column name)
            header_idx = None
            for i, line in enumerate(lines):
                if "Ticker" in line and "Name" in line:
                    header_idx = i
                    break

            if header_idx is None:
                logger.warning("Could not find data header in IWV CSV")
                return []

            # Parse CSV from the header row onward
            from io import StringIO
            csv_text = "\n".join(lines[header_idx:])
            df = pd.read_csv(StringIO(csv_text))

            # Normalize column names
            df.columns = [c.strip() for c in df.columns]
            ticker_col = next((c for c in df.columns if c.lower() == "ticker"), None)
            name_col = next((c for c in df.columns if "name" in c.lower()), None)
            sector_col = next((c for c in df.columns if "sector" in c.lower()), None)

            if ticker_col is None:
                logger.warning("No Ticker column found in IWV CSV")
                return []

            records = []
            now = datetime.now().isoformat()
            for _, row in df.iterrows():
                ticker = str(row.get(ticker_col, "")).strip()
                if not TICKER_PATTERN.match(ticker):
                    continue  # Skip cash, derivatives, footer rows
                name = str(row.get(name_col, "")) if name_col else ""
                sector = str(row.get(sector_col, "Unknown")) if sector_col else "Unknown"
                records.append({
                    "ticker": ticker,
                    "name": name.strip(),
                    "sector": sector.strip(),
                    "source": "iwv",
                    "updated_date": now,
                })

            logger.info(f"IWV download: {len(records)} valid equity tickers")
            return records

        except Exception as e:
            logger.error(f"IWV download error: {e}")
            return []

    def _scrape_wikipedia(self) -> List[Dict]:
        """
        Fallback: attempt to get Russell 3000 components from Wikipedia or
        construct a large-cap list from S&P 500 + additional known tickers.
        Returns a partial list when the primary source fails.
        """
        try:
            # Try Wikipedia S&P 500 table as a reasonable subset
            url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
            tables = pd.read_html(url)
            sp500_df = tables[0]

            ticker_col = "Symbol" if "Symbol" in sp500_df.columns else sp500_df.columns[0]
            name_col = "Security" if "Security" in sp500_df.columns else sp500_df.columns[1]
            sector_col = "GICS Sector" if "GICS Sector" in sp500_df.columns else None

            records = []
            now = datetime.now().isoformat()
            for _, row in sp500_df.iterrows():
                ticker = str(row[ticker_col]).strip().replace(".", "-")
                if not TICKER_PATTERN.match(ticker):
                    continue
                name = str(row[name_col]).strip() if name_col else ""
                sector = str(row[sector_col]).strip() if sector_col else "Unknown"
                records.append({
                    "ticker": ticker,
                    "name": name,
                    "sector": sector,
                    "source": "wikipedia_sp500",
                    "updated_date": now,
                })

            logger.info(f"Wikipedia S&P 500 fallback: {len(records)} tickers")
            return records
        except Exception as e:
            logger.error(f"Wikipedia fallback error: {e}")
            return []

    def _save_universe(self, records: List[Dict]) -> None:
        df = pd.DataFrame(records)
        save_parquet(df, self._data_category, self._filename)
