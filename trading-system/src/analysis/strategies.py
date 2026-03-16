"""
Strategy Engine.

Combines fundamental and technical analysis with fund-specific weights
to produce unified buy/sell recommendations per fund.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime

import pandas as pd
import numpy as np
from loguru import logger

from src.utils import (
    load_config, get_fund_config, get_all_tickers, get_sector,
    save_parquet, load_parquet, trading_date_str,
)
from src.analysis.technical import TechnicalAnalyzer
from src.analysis.fundamental import FundamentalAnalyzer
from src.analysis.risk_metrics import RiskMetrics
from src.collector.price_fetcher import PriceFetcher


class StrategyEngine:
    """
    Runs the three strategy funds, combining technical and fundamental
    analysis with fund-specific weights and risk parameters.
    """

    def __init__(self):
        self.config = load_config()
        self.funds = self.config.get("funds", {})
        self.technical = TechnicalAnalyzer()
        self.fundamental = FundamentalAnalyzer()
        self.risk_calc = RiskMetrics()
        self.price_fetcher = PriceFetcher()

    # ------------------------------------------------------------------
    # Main Analysis Pipeline
    # ------------------------------------------------------------------
    def run_analysis(self, tickers: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Run full analysis for all funds across all tickers.

        Returns dict keyed by fund name, each containing:
            - recommendations: sorted list of buy/sell/hold signals
            - portfolio_metrics: risk metrics for the fund
            - timestamp: when analysis ran
        """
        if tickers is None:
            tickers = get_all_tickers()

        logger.info(f"Running analysis on {len(tickers)} tickers across {len(self.funds)} funds")

        # Load data
        price_data = self.price_fetcher.load_price_history()
        fundamentals_data = self.price_fetcher.load_fundamentals()

        if price_data is None or price_data.empty:
            logger.error("No price data available. Run data collector first.")
            return {}

        # Pre-compute technical indicators per ticker
        tech_signals = {}
        for ticker in tickers:
            ticker_prices = price_data[price_data["ticker"] == ticker].copy()
            if len(ticker_prices) < 50:
                continue
            ticker_prices = self.technical.calculate_indicators(ticker_prices)
            signal = self.technical.generate_signals(ticker_prices)
            signal["ticker"] = ticker
            tech_signals[ticker] = signal

        # Pre-compute fundamental scores per ticker
        fund_signals = {}
        if fundamentals_data is not None:
            for ticker in tickers:
                ticker_fundamentals = fundamentals_data[fundamentals_data["ticker"] == ticker]
                if ticker_fundamentals.empty:
                    continue
                f_data = ticker_fundamentals.iloc[-1].to_dict()
                score = self.fundamental.score_stock(f_data)
                score["ticker"] = ticker
                fund_signals[ticker] = score

        # Generate per-fund recommendations
        results = {}
        for fund_name, fund_cfg in self.funds.items():
            logger.info(f"Generating recommendations for: {fund_cfg['name']}")
            recs = self._generate_fund_recommendations(
                fund_name, fund_cfg, tech_signals, fund_signals, price_data
            )
            results[fund_name] = {
                "fund_name": fund_cfg["name"],
                "recommendations": recs,
                "timestamp": datetime.now().isoformat(),
                "num_tickers_analyzed": len(tickers),
            }

        # Save analysis results
        self._save_results(results)

        return results

    def _generate_fund_recommendations(
        self,
        fund_name: str,
        fund_cfg: Dict,
        tech_signals: Dict,
        fund_signals: Dict,
        price_data: pd.DataFrame,
    ) -> List[Dict[str, Any]]:
        """Generate weighted recommendations for a specific fund."""
        weights = fund_cfg.get("weights", {"fundamental": 0.5, "technical": 0.5})
        w_tech = weights.get("technical", 0.5)
        w_fund = weights.get("fundamental", 0.5)
        risk_params = fund_cfg.get("risk_params", {})

        recommendations = []

        all_tickers = set(list(tech_signals.keys()) + list(fund_signals.keys()))

        for ticker in all_tickers:
            tech = tech_signals.get(ticker, {"signal": "HOLD", "confidence": 0, "score": 0})
            funda = fund_signals.get(ticker, {"signal": "HOLD", "confidence": 0, "normalized_score": 0.5})

            # Convert signals to numeric: BUY=1, HOLD=0, SELL=-1
            tech_numeric = {"BUY": 1, "HOLD": 0, "SELL": -1}.get(tech.get("signal", "HOLD"), 0)
            fund_numeric = {"BUY": 1, "HOLD": 0, "SELL": -1}.get(funda.get("signal", "HOLD"), 0)

            # Weighted composite score
            composite = (tech_numeric * tech.get("confidence", 0) * w_tech +
                         fund_numeric * funda.get("confidence", 0) * w_fund)

            # Weighted confidence
            confidence = (tech.get("confidence", 0) * w_tech +
                          funda.get("confidence", 0) * w_fund)

            # Determine combined signal
            if composite > 0.15:
                signal = "BUY"
            elif composite < -0.15:
                signal = "SELL"
            else:
                signal = "HOLD"

            # Get price targets from technical analysis
            entry_price = tech.get("entry_price", 0)
            stop_loss = tech.get("stop_loss", 0)
            target_price = tech.get("target_price", 0)

            # Adjust stop-loss based on fund risk params
            if entry_price > 0 and signal == "BUY":
                fund_stop_pct = risk_params.get("stop_loss_pct", 0.10)
                fund_stop = entry_price * (1 - fund_stop_pct)
                stop_loss = max(stop_loss, fund_stop)

            risk_reward = (
                abs(target_price - entry_price) / abs(entry_price - stop_loss)
                if entry_price > 0 and abs(entry_price - stop_loss) > 0
                else 0
            )

            # Combine reasons
            reasons = []
            if tech.get("reasons"):
                reasons.extend([f"[T] {r}" for r in tech["reasons"][:3]])
            if funda.get("reasons"):
                reasons.extend([f"[F] {r}" for r in funda["reasons"][:3]])

            rec = {
                "ticker": ticker,
                "signal": signal,
                "composite_score": round(composite, 3),
                "confidence": round(confidence, 3),
                "technical_signal": tech.get("signal", "HOLD"),
                "technical_confidence": tech.get("confidence", 0),
                "fundamental_signal": funda.get("signal", "HOLD"),
                "fundamental_confidence": funda.get("confidence", 0),
                "entry_price": round(entry_price, 2),
                "stop_loss": round(stop_loss, 2),
                "target_price": round(target_price, 2),
                "risk_reward_ratio": round(risk_reward, 2),
                "sector": get_sector(ticker),
                "reasons": reasons,
                "technical_indicators": tech.get("indicators", {}),
                "fundamental_metrics": funda.get("metrics", {}),
                "fund": fund_name,
                "date": trading_date_str(),
            }
            recommendations.append(rec)

        # Sort by composite score (best opportunities first)
        recommendations.sort(key=lambda x: abs(x["composite_score"]), reverse=True)

        return recommendations

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------
    def _save_results(self, results: Dict):
        """Save analysis results to Parquet."""
        all_recs = []
        for fund_name, data in results.items():
            for rec in data.get("recommendations", []):
                flat_rec = {k: v for k, v in rec.items()
                            if not isinstance(v, (dict, list))}
                flat_rec["reasons"] = "; ".join(rec.get("reasons", []))
                all_recs.append(flat_rec)

        if all_recs:
            df = pd.DataFrame(all_recs)
            save_parquet(df, "analysis", f"recommendations_{trading_date_str()}")
            save_parquet(df, "analysis", "recommendations_latest")
            logger.info(f"Saved {len(df)} recommendations")

    def load_latest_recommendations(self, fund_name: Optional[str] = None) -> Optional[pd.DataFrame]:
        """Load latest recommendations, optionally filtered by fund."""
        df = load_parquet("analysis", "recommendations_latest")
        if df is not None and fund_name:
            df = df[df["fund"] == fund_name]
        return df

    # ------------------------------------------------------------------
    # Convenience Methods
    # ------------------------------------------------------------------
    def get_top_buys(self, fund_name: str, n: int = 10) -> List[Dict]:
        """Get top N buy recommendations for a fund."""
        df = self.load_latest_recommendations(fund_name)
        if df is None or df.empty:
            return []
        buys = df[df["signal"] == "BUY"].sort_values("composite_score", ascending=False)
        return buys.head(n).to_dict("records")

    def get_top_sells(self, fund_name: str, n: int = 10) -> List[Dict]:
        """Get top N sell recommendations for a fund."""
        df = self.load_latest_recommendations(fund_name)
        if df is None or df.empty:
            return []
        sells = df[df["signal"] == "SELL"].sort_values("composite_score", ascending=True)
        return sells.head(n).to_dict("records")
