"""
Stock Screener — two-phase fundamental + technical filter.

Phase 1: Fetch yfinance .info for each ticker (parallel batches).
         Apply fundamental hard-cutoff filters.
         Score passers via FundamentalAnalyzer.score_stock().

Phase 2 (optional): Fetch 6-month price history for phase-1 passers.
         Run TechnicalAnalyzer.calculate_indicators() + generate_signals().
         Apply optional technical filter criteria.

Results are ranked by composite score (60% fundamental, 40% technical).
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yfinance as yf
import pandas as pd
from loguru import logger

from src.utils import load_config, get_data_dir, save_parquet, trading_date_str
from src.analysis.fundamental import FundamentalAnalyzer
from src.analysis.technical import TechnicalAnalyzer
from src.screener.universe import UniverseManager


# yfinance .info uses camelCase; FundamentalAnalyzer expects snake_case
_YFINANCE_TO_ANALYZER: dict = {
    "trailingPE":           "pe_ratio",
    "forwardPE":            "forward_pe",
    "pegRatio":             "peg_ratio",
    "priceToBook":          "price_to_book",
    "enterpriseToEbitda":   "ev_to_ebitda",
    "returnOnEquity":       "roe",
    "returnOnAssets":       "roa",
    "profitMargins":        "profit_margin",
    "operatingMargins":     "operating_margin",
    "revenueGrowth":        "revenue_growth",
    "earningsGrowth":       "earnings_growth",
    "debtToEquity":         "debt_to_equity",
    "currentRatio":         "current_ratio",
    "dividendYield":        "dividend_yield",
    "freeCashflow":         "free_cash_flow",
    "marketCap":            "market_cap",
    "beta":                 "beta",
}


# Columns to persist in the fundamentals cache (camelCase yfinance keys + display fields)
_CACHE_COLUMNS = list(_YFINANCE_TO_ANALYZER.keys()) + [
    "longName", "shortName", "sector", "sectorDisp", "industry",
]


class StockScreener:
    """Two-phase Russell 3000 screener."""

    def __init__(self):
        cfg = load_config()
        self.screener_cfg = cfg.get("screener", {})
        self.phase1_batch_size = self.screener_cfg.get("phase1_batch_size", 50)
        self.phase1_delay = self.screener_cfg.get("phase1_delay_seconds", 1.0)
        self.phase2_batch_size = self.screener_cfg.get("phase2_batch_size", 10)
        self.phase2_delay = self.screener_cfg.get("phase2_delay_seconds", 2.0)
        self.phase2_period = self.screener_cfg.get("phase2_history_period", "6mo")
        self.max_phase1_results = self.screener_cfg.get("max_phase1_results", 300)
        self.max_final_results = self.screener_cfg.get("max_final_results", 100)

        self.fundamental_analyzer = FundamentalAnalyzer()
        self.technical_analyzer = TechnicalAnalyzer()
        self.universe_mgr = UniverseManager()

        # Progress tracking (updated during run for API polling)
        self.progress: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Fundamentals Cache
    # ------------------------------------------------------------------
    def _cache_path(self) -> Path:
        return get_data_dir() / "screener" / f"fundamentals_cache_{trading_date_str()}.parquet"

    def _load_fundamentals_cache(self) -> Optional[Dict[str, Dict]]:
        """Load today's fundamentals cache. Returns {ticker: info_dict} or None."""
        path = self._cache_path()
        if not path.exists():
            return None
        age_hours = (time.time() - path.stat().st_mtime) / 3600
        if age_hours > 24:
            return None
        try:
            df = pd.read_parquet(path)
            result = {}
            for _, row in df.iterrows():
                ticker = row["_ticker"]
                result[ticker] = row.drop("_ticker").to_dict()
            logger.info(f"Fundamentals cache hit: {len(result)} tickers ({age_hours:.1f}h old)")
            return result
        except Exception as e:
            logger.warning(f"Cache load error: {e}")
            return None

    def _save_fundamentals_cache(self, ticker_info_map: Dict[str, Dict]) -> None:
        """Save fetched .info dicts to today's cache parquet."""
        try:
            rows = []
            for ticker, info in ticker_info_map.items():
                row = {"_ticker": ticker}
                for col in _CACHE_COLUMNS:
                    row[col] = info.get(col)
                rows.append(row)
            df = pd.DataFrame(rows)
            path = self._cache_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(path, index=False)
            logger.info(f"Fundamentals cache saved: {len(rows)} tickers → {path.name}")
        except Exception as e:
            logger.warning(f"Cache save error: {e}")

    def warm_cache(self, tickers: Optional[List[str]] = None) -> Dict[str, Any]:
        """Pre-warm the fundamentals cache. Returns status dict."""
        if tickers is None:
            tickers = self.universe_mgr.get_universe()
        start = time.time()
        all_fetched: Dict[str, Dict] = {}
        batches = [tickers[i:i + self.phase1_batch_size]
                   for i in range(0, len(tickers), self.phase1_batch_size)]
        for batch_num, batch in enumerate(batches):
            batch_results = self._fetch_fundamentals_batch(batch)
            for ticker, info in batch_results.items():
                if info is not None:
                    all_fetched[ticker] = info
            if batch_num < len(batches) - 1:
                time.sleep(self.phase1_delay)
        self._save_fundamentals_cache(all_fetched)
        return {
            "tickers_cached": len(all_fetched),
            "duration_seconds": round(time.time() - start, 1),
        }

    # ------------------------------------------------------------------
    # Main Entry Point
    # ------------------------------------------------------------------
    def run_screen(
        self,
        criteria: Dict[str, Any],
        include_technical: bool = True,
        tickers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Run the two-phase screen.

        Args:
            criteria: dict of filter thresholds (see ScreenerCriteria in api/models/screener.py)
            include_technical: whether to run phase 2 (slower)
            tickers: override the Russell 3000 universe with a custom list

        Returns:
            dict with results list and metadata
        """
        start_time = time.time()

        # Get universe
        if tickers is None:
            universe = self.universe_mgr.get_universe()
        else:
            universe = [t.upper() for t in tickers]

        logger.info(f"Screening {len(universe)} tickers | technical={include_technical}")

        # Phase 1: Fundamental filter
        self.progress = {"phase": "phase1", "count": 0, "total": len(universe)}
        phase1_passers = self._phase1_fundamental_screen(universe, criteria)
        logger.info(f"Phase 1 complete: {len(phase1_passers)}/{len(universe)} passed fundamental filter")

        # Phase 2: Technical filter (optional)
        if include_technical and phase1_passers:
            capped = phase1_passers[:self.max_phase1_results]
            self.progress = {"phase": "phase2", "count": 0, "total": len(capped)}
            phase2_passers = self._phase2_technical_screen(capped, criteria)
            logger.info(f"Phase 2 complete: {len(phase2_passers)}/{len(capped)} passed technical filter")
        else:
            phase2_passers = phase1_passers

        # Score and rank
        ranked = self._score_and_rank(phase2_passers)

        elapsed = time.time() - start_time

        # Cache results
        if ranked:
            df = pd.DataFrame([{
                k: v for k, v in r.items() if not isinstance(v, dict)
            } for r in ranked])
            save_parquet(df, "screener", f"screen_results_{trading_date_str()}")

        self.progress = {"phase": "complete", "count": len(ranked), "total": len(universe)}

        return {
            "results": ranked,
            "phase1_count": len(phase1_passers),
            "phase2_count": len(phase2_passers),
            "total_screened": len(universe),
            "duration_seconds": round(elapsed, 1),
            "timestamp": datetime.now().isoformat(),
            "criteria_used": criteria,
        }

    # ------------------------------------------------------------------
    # Phase 1: Fundamental Filter
    # ------------------------------------------------------------------
    def _phase1_fundamental_screen(
        self, tickers: List[str], criteria: Dict[str, Any]
    ) -> List[Dict]:
        """
        Fetch .info for each ticker using a thread pool (5 workers).
        Apply hard-cutoff fundamental filters from criteria dict.
        Score passers via FundamentalAnalyzer.
        Uses today's fundamentals cache when available (fast path).
        """
        passers = []

        # --- Fast path: use today's fundamentals cache ---
        cache = self._load_fundamentals_cache()
        if cache is not None:
            for i, ticker in enumerate(tickers):
                self.progress["count"] = i + 1
                info = cache.get(ticker)
                if info is None:
                    continue
                if not self._passes_fundamental_filters(info, criteria):
                    continue
                try:
                    score_result = self.fundamental_analyzer.score_stock(
                        self._normalize_info_for_scoring(info)
                    )
                except Exception:
                    score_result = {"normalized_score": 0.0, "signal": "HOLD",
                                    "confidence": 0.0, "metrics": {}, "reasons": []}
                sector = info.get("sector") or info.get("sectorDisp") or "Unknown"
                sectors_include = criteria.get("sectors_include", [])
                sectors_exclude = criteria.get("sectors_exclude", [])
                if sectors_include and sector not in sectors_include:
                    continue
                if sectors_exclude and sector in sectors_exclude:
                    continue
                passers.append({
                    "ticker": ticker,
                    "name": info.get("longName") or info.get("shortName") or ticker,
                    "sector": sector,
                    "fundamental_score": score_result.get("total_score", 0.0),
                    "fundamental_confidence": score_result.get("confidence", 0.0),
                    "fundamental_signal": score_result.get("signal", "HOLD"),
                    "technical_signal": None,
                    "technical_confidence": 0.0,
                    "composite_score": 0.0,
                    "metrics": score_result.get("metrics", {}),
                    "reasons": score_result.get("reasons", []),
                    "_info": info,
                })
            return passers

        # --- Slow path: fetch live from yfinance, save cache after ---
        all_fetched: Dict[str, Dict] = {}
        batches = [tickers[i:i + self.phase1_batch_size]
                   for i in range(0, len(tickers), self.phase1_batch_size)]

        processed = 0
        for batch_num, batch in enumerate(batches):
            batch_results = self._fetch_fundamentals_batch(batch)

            for ticker, info in batch_results.items():
                processed += 1
                self.progress["count"] = processed

                if info is None:
                    continue

                all_fetched[ticker] = info  # accumulate for cache

                # Apply hard-cutoff filters
                if not self._passes_fundamental_filters(info, criteria):
                    continue

                # Score via FundamentalAnalyzer (needs snake_case keys)
                try:
                    score_result = self.fundamental_analyzer.score_stock(
                        self._normalize_info_for_scoring(info)
                    )
                except Exception:
                    score_result = {"normalized_score": 0.0, "signal": "HOLD",
                                    "confidence": 0.0, "metrics": {}, "reasons": []}

                # Extract sector from info or criteria
                sector = info.get("sector") or info.get("sectorDisp") or "Unknown"

                # Apply sector filters
                sectors_include = criteria.get("sectors_include", [])
                sectors_exclude = criteria.get("sectors_exclude", [])
                if sectors_include and sector not in sectors_include:
                    continue
                if sectors_exclude and sector in sectors_exclude:
                    continue

                passers.append({
                    "ticker": ticker,
                    "name": info.get("longName") or info.get("shortName") or ticker,
                    "sector": sector,
                    "fundamental_score": score_result.get("total_score", 0.0),
                    "fundamental_confidence": score_result.get("confidence", 0.0),
                    "fundamental_signal": score_result.get("signal", "HOLD"),
                    "technical_signal": None,
                    "technical_confidence": 0.0,
                    "composite_score": 0.0,
                    "metrics": score_result.get("metrics", {}),
                    "reasons": score_result.get("reasons", []),
                    "_info": info,  # keep for phase 2 filtering
                })

            if batch_num < len(batches) - 1:
                time.sleep(self.phase1_delay)

        # Save fetched data for reuse within the same trading day
        self._save_fundamentals_cache(all_fetched)
        return passers

    def _normalize_info_for_scoring(self, info: Dict) -> Dict:
        """Translate yfinance .info camelCase keys → FundamentalAnalyzer snake_case keys."""
        return {snake: info.get(camel) for camel, snake in _YFINANCE_TO_ANALYZER.items()}

    def _passes_fundamental_filters(self, info: Dict, criteria: Dict) -> bool:
        """
        Apply hard-cutoff filters. A None metric means unknown → pass through.
        """
        checks = [
            ("trailingPE",        criteria.get("pe_ratio_max"),        "max"),
            ("pegRatio",          criteria.get("peg_ratio_max"),        "max"),
            ("returnOnEquity",    criteria.get("roe_min"),              "min"),
            ("returnOnAssets",    criteria.get("roa_min"),              "min"),
            ("debtToEquity",      criteria.get("debt_to_equity_max"),   "max"),
            ("currentRatio",      criteria.get("current_ratio_min"),    "min"),
            ("revenueGrowth",     criteria.get("revenue_growth_min"),   "min"),
            ("profitMargins",     criteria.get("profit_margin_min"),    "min"),
            ("earningsGrowth",    criteria.get("earnings_growth_min"),  "min"),
            ("marketCap",         criteria.get("market_cap_min"),       "min"),
            ("marketCap",         criteria.get("market_cap_max"),       "max"),
        ]

        for field, threshold, direction in checks:
            if threshold is None:
                continue
            value = info.get(field)
            if value is None:
                continue  # Unknown — pass through
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if direction == "max" and value > threshold:
                return False
            if direction == "min" and value < threshold:
                return False

        return True

    def _fetch_fundamentals_batch(self, tickers: List[str]) -> Dict[str, Optional[Dict]]:
        """Fetch .info for a batch using ThreadPoolExecutor."""
        results = {}

        def _fetch_one(ticker: str):
            try:
                t = yf.Ticker(ticker)
                info = t.info
                # yfinance returns minimal dict for invalid tickers
                if info and len(info) > 5:
                    return ticker, info
                return ticker, None
            except Exception:
                return ticker, None

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(_fetch_one, t): t for t in tickers}
            for future in as_completed(futures):
                try:
                    ticker, info = future.result()
                    results[ticker] = info
                except Exception:
                    results[futures[future]] = None

        return results

    # ------------------------------------------------------------------
    # Phase 2: Technical Filter
    # ------------------------------------------------------------------
    def _phase2_technical_screen(
        self, candidates: List[Dict], criteria: Dict[str, Any]
    ) -> List[Dict]:
        """
        Fetch price history for phase-1 passers in batches.
        Run TechnicalAnalyzer on each. Apply optional technical filters.
        """
        tickers = [c["ticker"] for c in candidates]
        candidate_map = {c["ticker"]: c for c in candidates}
        passers = []

        batches = [tickers[i:i + self.phase2_batch_size]
                   for i in range(0, len(tickers), self.phase2_batch_size)]

        processed = 0
        for batch_num, batch in enumerate(batches):
            try:
                price_data = yf.download(
                    batch,
                    period=self.phase2_period,
                    interval="1d",
                    auto_adjust=True,
                    progress=False,
                    threads=True,
                )
            except Exception as e:
                logger.warning(f"Price download error for batch: {e}")
                price_data = pd.DataFrame()

            for ticker in batch:
                processed += 1
                self.progress["count"] = processed
                candidate = dict(candidate_map[ticker])

                try:
                    # Extract ticker-specific DataFrame from multi-index download
                    if isinstance(price_data.columns, pd.MultiIndex):
                        if ticker not in price_data.columns.get_level_values(1):
                            passers.append(candidate)
                            continue
                        ticker_df = price_data.xs(ticker, axis=1, level=1).reset_index()
                    else:
                        ticker_df = price_data.reset_index()

                    ticker_df = ticker_df.rename(columns={
                        "Date": "date", "Open": "open", "High": "high",
                        "Low": "low", "Close": "close", "Volume": "volume",
                    })
                    ticker_df["ticker"] = ticker
                    ticker_df = ticker_df.dropna(subset=["close"])

                    if len(ticker_df) < 30:
                        passers.append(candidate)
                        continue

                    # Calculate indicators and generate signal
                    ticker_df = self.technical_analyzer.calculate_indicators(ticker_df)
                    signal = self.technical_analyzer.generate_signals(ticker_df)

                    # Apply technical filters
                    if not self._passes_technical_filters(ticker_df, signal, criteria):
                        continue

                    candidate["technical_signal"] = signal.get("signal", "HOLD")
                    candidate["technical_confidence"] = signal.get("confidence", 0.0)
                    passers.append(candidate)

                except Exception as e:
                    logger.debug(f"Technical analysis error for {ticker}: {e}")
                    passers.append(candidate)

            if batch_num < len(batches) - 1:
                time.sleep(self.phase2_delay)

        return passers

    def _passes_technical_filters(
        self, df: pd.DataFrame, signal: Dict, criteria: Dict
    ) -> bool:
        """Apply optional technical filter criteria."""
        last = df.iloc[-1]

        # Above 200-day SMA filter
        if criteria.get("require_above_sma200"):
            sma200 = last.get("sma_trend")
            close = last.get("close")
            if sma200 is not None and close is not None:
                if float(close) < float(sma200):
                    return False

        # Bullish MACD filter
        if criteria.get("require_bullish_macd"):
            macd = last.get("macd")
            macd_signal = last.get("macd_signal")
            if macd is not None and macd_signal is not None:
                if float(macd) <= float(macd_signal):
                    return False

        # RSI range filter
        rsi = last.get("rsi")
        if rsi is not None:
            rsi_val = float(rsi)
            rsi_max = criteria.get("rsi_max")
            rsi_min = criteria.get("rsi_min")
            if rsi_max is not None and rsi_val > rsi_max:
                return False
            if rsi_min is not None and rsi_val < rsi_min:
                return False

        # ADX minimum filter (trend strength)
        min_adx = criteria.get("min_adx")
        if min_adx is not None:
            adx = last.get("adx")
            if adx is not None and float(adx) < min_adx:
                return False

        return True

    # ------------------------------------------------------------------
    # Scoring & Ranking
    # ------------------------------------------------------------------
    def _score_and_rank(self, candidates: List[Dict]) -> List[Dict]:
        """Compute composite score and sort descending."""
        for c in candidates:
            fund_score = c.get("fundamental_score", 0.0) / 100.0  # normalize to 0-1
            tech_conf = c.get("technical_confidence", 0.0)

            # Weight: 60% fundamental, 40% technical (when technical available)
            if c.get("technical_signal") is not None:
                composite = fund_score * 0.60 + tech_conf * 0.40
            else:
                composite = fund_score

            c["composite_score"] = round(composite, 4)
            # Remove internal _info key before returning
            c.pop("_info", None)

        ranked = sorted(candidates, key=lambda x: x["composite_score"], reverse=True)
        return ranked[:self.max_final_results]
