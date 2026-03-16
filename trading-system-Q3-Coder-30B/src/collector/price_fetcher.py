"""
Price Fetcher: Collects market data via yfinance and stores in Parquet.
Pulls prices 3x daily, maintains historical data, and fetches fundamentals.
"""

import time
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any

import numpy as np
import pandas as pd
import yfinance as yf
from loguru import logger

from src.utils import (
    load_config, get_all_tickers, save_parquet, load_parquet,
    append_parquet, setup_logging, trading_date_str,
)


class PriceFetcher:
    """Fetches and stores price data from yfinance."""

    def __init__(self):
        self.config = load_config()
        self.data_cfg = self.config.get("data_collection", {})
        self.batch_size = self.data_cfg.get("batch_size", 10)
        self.max_retries = self.data_cfg.get("max_retries", 3)
        self.retry_delay = self.data_cfg.get("retry_delay_seconds", 5)

    # ------------------------------------------------------------------
    # Core Price Collection
    # ------------------------------------------------------------------
    def fetch_current_prices(self, tickers: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Fetch current prices for all watchlist tickers.
        Returns DataFrame with columns: ticker, datetime, open, high, low,
        close, volume, pull_session.
        """
        if tickers is None:
            tickers = get_all_tickers()

        logger.info(f"Fetching current prices for {len(tickers)} tickers")
        all_rows = []
        now = datetime.now()
        session = self._determine_session(now)

        # Batch fetch
        for i in range(0, len(tickers), self.batch_size):
            batch = tickers[i : i + self.batch_size]
            batch_str = " ".join(batch)

            for attempt in range(self.max_retries):
                try:
                    data = yf.download(
                        batch_str,
                        period="5d",
                        interval="1d",
                        group_by="ticker",
                        progress=False,
                        threads=True,
                    )

                    if data.empty:
                        logger.warning(f"No data returned for batch: {batch}")
                        break

                    for ticker in batch:
                        try:
                            if len(batch) == 1:
                                ticker_data = data
                            else:
                                ticker_data = data[ticker]

                            if ticker_data.empty:
                                continue

                            latest = ticker_data.iloc[-1]
                            row = {
                                "ticker": ticker,
                                "date": trading_date_str(),
                                "datetime": now.isoformat(),
                                "open": float(latest.get("Open", np.nan)),
                                "high": float(latest.get("High", np.nan)),
                                "low": float(latest.get("Low", np.nan)),
                                "close": float(latest.get("Close", np.nan)),
                                "volume": int(latest.get("Volume", 0)),
                                "pull_session": session,
                            }
                            all_rows.append(row)
                        except Exception as e:
                            logger.warning(f"Error processing {ticker}: {e}")

                    break  # Success
                except Exception as e:
                    logger.warning(f"Attempt {attempt + 1} failed for batch: {e}")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay)

            time.sleep(1)  # Rate limiting between batches

        df = pd.DataFrame(all_rows)
        if not df.empty:
            logger.info(f"Fetched prices for {len(df)} tickers")
        return df

    def fetch_historical_prices(
        self,
        tickers: Optional[List[str]] = None,
        period: str = "1y",
        interval: str = "1d",
    ) -> pd.DataFrame:
        """
        Fetch historical daily price data.
        Returns DataFrame: ticker, date, open, high, low, close, adj_close, volume.
        """
        if tickers is None:
            tickers = get_all_tickers()

        logger.info(f"Fetching historical prices ({period}) for {len(tickers)} tickers")
        all_rows = []

        for i in range(0, len(tickers), self.batch_size):
            batch = tickers[i : i + self.batch_size]
            batch_str = " ".join(batch)

            for attempt in range(self.max_retries):
                try:
                    data = yf.download(
                        batch_str,
                        period=period,
                        interval=interval,
                        group_by="ticker",
                        progress=False,
                        threads=True,
                    )

                    if data.empty:
                        break

                    for ticker in batch:
                        try:
                            if len(batch) == 1:
                                ticker_data = data
                            else:
                                ticker_data = data[ticker]

                            if ticker_data.empty or ticker_data.dropna(how="all").empty:
                                continue

                            for idx, row in ticker_data.iterrows():
                                if pd.isna(row.get("Close")):
                                    continue
                                all_rows.append({
                                    "ticker": ticker,
                                    "date": idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx),
                                    "open": float(row.get("Open", np.nan)),
                                    "high": float(row.get("High", np.nan)),
                                    "low": float(row.get("Low", np.nan)),
                                    "close": float(row.get("Close", np.nan)),
                                    "volume": int(row.get("Volume", 0)),
                                })
                        except Exception as e:
                            logger.warning(f"Error processing historical {ticker}: {e}")

                    break
                except Exception as e:
                    logger.warning(f"Historical attempt {attempt + 1} failed: {e}")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay)

            time.sleep(1)

        df = pd.DataFrame(all_rows)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            logger.info(f"Fetched {len(df)} historical price records")
        return df

    def fetch_fundamentals(
        self, tickers: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Fetch fundamental data for all tickers via yfinance .info.
        Returns DataFrame with key fundamental metrics.
        """
        if tickers is None:
            tickers = get_all_tickers()

        logger.info(f"Fetching fundamentals for {len(tickers)} tickers")
        rows = []

        for ticker in tickers:
            try:
                stock = yf.Ticker(ticker)
                info = stock.info or {}

                row = {
                    "ticker": ticker,
                    "date": trading_date_str(),
                    "market_cap": info.get("marketCap"),
                    "pe_ratio": info.get("trailingPE"),
                    "forward_pe": info.get("forwardPE"),
                    "peg_ratio": info.get("pegRatio"),
                    "price_to_book": info.get("priceToBook"),
                    "price_to_sales": info.get("priceToSalesTrailing12Months"),
                    "enterprise_value": info.get("enterpriseValue"),
                    "ev_to_ebitda": info.get("enterpriseToEbitda"),
                    "revenue": info.get("totalRevenue"),
                    "revenue_growth": info.get("revenueGrowth"),
                    "earnings_growth": info.get("earningsGrowth"),
                    "profit_margin": info.get("profitMargins"),
                    "operating_margin": info.get("operatingMargins"),
                    "roe": info.get("returnOnEquity"),
                    "roa": info.get("returnOnAssets"),
                    "debt_to_equity": info.get("debtToEquity"),
                    "current_ratio": info.get("currentRatio"),
                    "quick_ratio": info.get("quickRatio"),
                    "free_cash_flow": info.get("freeCashflow"),
                    "dividend_yield": info.get("dividendYield"),
                    "beta": info.get("beta"),
                    "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                    "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
                    "avg_volume": info.get("averageVolume"),
                    "sector": info.get("sector", "Unknown"),
                    "industry": info.get("industry", "Unknown"),
                }
                rows.append(row)
                time.sleep(0.5)  # Rate limiting

            except Exception as e:
                logger.warning(f"Failed to fetch fundamentals for {ticker}: {e}")

        df = pd.DataFrame(rows)
        if not df.empty:
            # Convert debt_to_equity from percentage to ratio if needed
            if "debt_to_equity" in df.columns:
                mask = df["debt_to_equity"] > 10
                df.loc[mask, "debt_to_equity"] = df.loc[mask, "debt_to_equity"] / 100
            logger.info(f"Fetched fundamentals for {len(df)} tickers")
        return df

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------
    def save_prices(self, df: pd.DataFrame, price_type: str = "daily"):
        """Save price data to Parquet."""
        if df.empty:
            return
        filename = f"prices_{price_type}"
        append_parquet(df, "prices", filename)
        logger.info(f"Saved {len(df)} price records to {filename}")

    def save_intraday_snapshot(self, df: pd.DataFrame):
        """Save intraday price snapshot."""
        if df.empty:
            return
        filename = f"snapshot_{trading_date_str()}"
        append_parquet(df, "prices", filename)
        logger.info(f"Saved intraday snapshot: {len(df)} records")

    def save_fundamentals(self, df: pd.DataFrame):
        """Save fundamental data to Parquet."""
        if df.empty:
            return
        save_parquet(df, "analysis", "fundamentals")
        logger.info(f"Saved fundamentals for {len(df)} tickers")

    def load_price_history(self, ticker: Optional[str] = None) -> Optional[pd.DataFrame]:
        """Load historical price data, optionally filtered by ticker."""
        df = load_parquet("prices", "prices_daily")
        if df is not None and ticker:
            df = df[df["ticker"] == ticker]
        return df

    def load_fundamentals(self) -> Optional[pd.DataFrame]:
        """Load cached fundamental data."""
        return load_parquet("analysis", "fundamentals")

    # ------------------------------------------------------------------
    # Full Collection Run
    # ------------------------------------------------------------------
    def run_price_pull(self):
        """Execute a full price pull cycle."""
        logger.info("=" * 60)
        logger.info("Starting price pull cycle")
        logger.info("=" * 60)

        # Current prices
        current = self.fetch_current_prices()
        if not current.empty:
            self.save_intraday_snapshot(current)

        # Check if we need historical data
        existing = self.load_price_history()
        if existing is None or len(existing) < 100:
            logger.info("Fetching full historical data...")
            historical = self.fetch_historical_prices(period="2y")
            if not historical.empty:
                self.save_prices(historical, "daily")
        else:
            # Just append today's data to daily
            if not current.empty:
                daily = current[["ticker", "date", "open", "high", "low", "close", "volume"]].copy()
                self.save_prices(daily, "daily")

        logger.info("Price pull cycle complete")

    def run_fundamentals_pull(self):
        """Execute a fundamentals fetch cycle."""
        logger.info("=" * 60)
        logger.info("Starting fundamentals pull")
        logger.info("=" * 60)

        fundamentals = self.fetch_fundamentals()
        if not fundamentals.empty:
            self.save_fundamentals(fundamentals)

        logger.info("Fundamentals pull complete")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _determine_session(dt: datetime) -> str:
        """Determine which pull session based on time."""
        hour = dt.hour
        if hour < 11:
            return "morning"
        elif hour < 14:
            return "midday"
        else:
            return "closing"
