"""
Backtesting Engine.

Tests strategies on historical data with configurable date ranges,
slippage/commission modeling, stop-loss/take-profit triggers,
and benchmark comparison vs SPY.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from loguru import logger

from src.utils import (
    load_config, save_parquet, load_parquet, get_sector, get_all_tickers,
)
from src.analysis.technical import TechnicalAnalyzer
from src.analysis.fundamental import FundamentalAnalyzer
from src.analysis.risk_metrics import RiskMetrics
from src.collector.price_fetcher import PriceFetcher


class BacktestEngine:
    """
    Simulates strategy execution on historical data.
    """

    def __init__(self):
        self.config = load_config()
        bt_cfg = self.config.get("backtest", {})
        self.slippage_pct = bt_cfg.get("slippage_pct", 0.001)
        self.commission_pct = bt_cfg.get("commission_pct", 0.0001)
        self.commission_flat = bt_cfg.get("commission_per_trade", 0.0)
        self.initial_capital = bt_cfg.get("initial_capital", 100000)
        self.benchmark_ticker = bt_cfg.get("benchmark", "SPY")
        self.risk_free_rate = bt_cfg.get("risk_free_rate", 0.05)
        self.min_trade_interval = bt_cfg.get("min_trade_interval_days", 1)

        self.technical = TechnicalAnalyzer()
        self.fundamental = FundamentalAnalyzer()
        self.risk_calc = RiskMetrics()

    # ------------------------------------------------------------------
    # Main Backtest Runner
    # ------------------------------------------------------------------
    def run_backtest(
        self,
        fund_name: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        tickers: Optional[List[str]] = None,
        initial_capital: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Run a full backtest for a specific fund strategy.

        Returns dict with:
            equity_curve: DataFrame of daily portfolio values
            trade_log: DataFrame of all executed trades
            metrics: comprehensive performance metrics
            benchmark_metrics: SPY benchmark comparison
        """
        bt_cfg = self.config.get("backtest", {})
        if start_date is None:
            start_date = bt_cfg.get("default_start_date", "2023-01-01")
        if end_date is None:
            end_date = bt_cfg.get("default_end_date", "2025-01-01")
        if initial_capital is None:
            initial_capital = self.initial_capital

        fund_cfg = self.config["funds"][fund_name]
        weights = fund_cfg.get("weights", {"fundamental": 0.5, "technical": 0.5})
        risk_params = fund_cfg.get("risk_params", {})

        if tickers is None:
            tickers = get_all_tickers()[:20]  # Limit for backtest speed

        logger.info(f"Running backtest: {fund_cfg['name']}")
        logger.info(f"  Period: {start_date} to {end_date}")
        logger.info(f"  Tickers: {len(tickers)}, Capital: ${initial_capital:,.0f}")

        # Load & prepare historical data
        fetcher = PriceFetcher()
        all_prices = fetcher.load_price_history()

        if all_prices is None or all_prices.empty:
            logger.info("No cached prices, fetching from yfinance...")
            all_prices = fetcher.fetch_historical_prices(
                tickers + [self.benchmark_ticker], period="5y"
            )
            if not all_prices.empty:
                fetcher.save_prices(all_prices, "daily")

        if all_prices is None or all_prices.empty:
            logger.error("No price data available for backtest")
            return {"error": "No price data"}

        # Filter date range
        all_prices["date"] = pd.to_datetime(all_prices["date"])
        mask = (all_prices["date"] >= start_date) & (all_prices["date"] <= end_date)
        all_prices = all_prices[mask].copy()

        # Get unique dates
        dates = sorted(all_prices["date"].unique())
        if len(dates) < 50:
            logger.error("Insufficient date range for backtest")
            return {"error": "Insufficient data"}

        logger.info(f"  Trading days: {len(dates)}")

        # ------------------------------------------------------------------
        # Simulation Loop
        # ------------------------------------------------------------------
        cash = initial_capital
        positions = {}     # {ticker: {quantity, avg_cost, stop_loss, target, trailing_stop}}
        trade_log = []
        equity_curve = []

        # Pre-calculate technical indicators for all tickers
        ticker_data = {}
        for ticker in tickers:
            t_prices = all_prices[all_prices["ticker"] == ticker].sort_values("date")
            if len(t_prices) >= 50:
                t_prices = self.technical.calculate_indicators(t_prices)
                ticker_data[ticker] = t_prices

        last_trade_date = {}

        for i, current_date in enumerate(dates):
            date_str = current_date.strftime("%Y-%m-%d")

            # Get current prices for this date
            day_prices = all_prices[all_prices["date"] == current_date]
            price_map = dict(zip(day_prices["ticker"], day_prices["close"]))

            # --- Update Positions & Check Stops ---
            for ticker in list(positions.keys()):
                if ticker not in price_map:
                    continue

                current_price = price_map[ticker]
                pos = positions[ticker]

                # Update trailing stop
                trailing_pct = risk_params.get("trailing_stop_pct", 0.08)
                new_trailing = current_price * (1 - trailing_pct)
                pos["trailing_stop"] = max(pos.get("trailing_stop", 0), new_trailing)

                effective_stop = max(pos.get("stop_loss", 0), pos.get("trailing_stop", 0))

                # Check stop-loss
                if current_price <= effective_stop:
                    sell_price = current_price * (1 - self.slippage_pct)
                    pnl = (sell_price - pos["avg_cost"]) * pos["quantity"]
                    commission = max(sell_price * pos["quantity"] * self.commission_pct, self.commission_flat)

                    trade_log.append({
                        "date": date_str, "action": "SELL", "ticker": ticker,
                        "quantity": pos["quantity"], "price": sell_price,
                        "pnl": pnl - commission, "pnl_pct": sell_price / pos["avg_cost"] - 1,
                        "reason": "stop_loss", "commission": commission,
                    })
                    cash += sell_price * pos["quantity"] - commission
                    del positions[ticker]
                    continue

                # Check take-profit
                if pos.get("target") and current_price >= pos["target"]:
                    sell_price = current_price * (1 - self.slippage_pct)
                    pnl = (sell_price - pos["avg_cost"]) * pos["quantity"]
                    commission = max(sell_price * pos["quantity"] * self.commission_pct, self.commission_flat)

                    trade_log.append({
                        "date": date_str, "action": "SELL", "ticker": ticker,
                        "quantity": pos["quantity"], "price": sell_price,
                        "pnl": pnl - commission, "pnl_pct": sell_price / pos["avg_cost"] - 1,
                        "reason": "take_profit", "commission": commission,
                    })
                    cash += sell_price * pos["quantity"] - commission
                    del positions[ticker]
                    continue

            # --- Generate Signals (every N days to reduce noise) ---
            signal_interval = 5  # Re-evaluate weekly
            if i % signal_interval == 0 and i >= 50:
                signals = []
                for ticker in tickers:
                    if ticker not in ticker_data:
                        continue

                    t_data = ticker_data[ticker]
                    hist = t_data[t_data["date"] <= current_date]
                    if len(hist) < 50:
                        continue

                    # Technical signal
                    tech_signal = self.technical.generate_signals(hist)

                    # Combine (simplified for backtesting speed)
                    tech_numeric = {"BUY": 1, "HOLD": 0, "SELL": -1}.get(tech_signal["signal"], 0)
                    composite = tech_numeric * tech_signal.get("confidence", 0)

                    signals.append({
                        "ticker": ticker,
                        "signal": tech_signal["signal"],
                        "composite": composite,
                        "confidence": tech_signal.get("confidence", 0),
                        "entry_price": tech_signal.get("entry_price", 0),
                        "stop_loss": tech_signal.get("stop_loss", 0),
                        "target_price": tech_signal.get("target_price", 0),
                    })

                # Process signals
                signals.sort(key=lambda x: x["composite"], reverse=True)

                # Sell signals first
                for sig in signals:
                    if sig["signal"] == "SELL" and sig["ticker"] in positions:
                        ticker = sig["ticker"]
                        if ticker not in price_map:
                            continue

                        sell_price = price_map[ticker] * (1 - self.slippage_pct)
                        pos = positions[ticker]
                        pnl = (sell_price - pos["avg_cost"]) * pos["quantity"]
                        commission = max(sell_price * pos["quantity"] * self.commission_pct, self.commission_flat)

                        trade_log.append({
                            "date": date_str, "action": "SELL", "ticker": ticker,
                            "quantity": pos["quantity"], "price": sell_price,
                            "pnl": pnl - commission, "pnl_pct": sell_price / pos["avg_cost"] - 1,
                            "reason": "signal_sell", "commission": commission,
                        })
                        cash += sell_price * pos["quantity"] - commission
                        del positions[ticker]

                # Buy signals
                max_positions = 10
                for sig in signals:
                    if sig["signal"] != "BUY" or sig["confidence"] < 0.3:
                        continue
                    if len(positions) >= max_positions:
                        break

                    ticker = sig["ticker"]
                    if ticker in positions or ticker not in price_map:
                        continue

                    # Check trade interval
                    last = last_trade_date.get(ticker)
                    if last and (current_date - last).days < self.min_trade_interval:
                        continue

                    # Position sizing (2% risk)
                    buy_price = price_map[ticker] * (1 + self.slippage_pct)
                    stop = sig.get("stop_loss", buy_price * 0.9)
                    risk_per_share = buy_price - stop
                    if risk_per_share <= 0:
                        continue

                    portfolio_value = cash + sum(
                        price_map.get(t, p["avg_cost"]) * p["quantity"]
                        for t, p in positions.items()
                    )
                    max_risk = portfolio_value * risk_params.get("max_risk_per_trade", 0.02)
                    quantity = int(max_risk / risk_per_share)

                    # Cap by position size
                    max_pos_val = portfolio_value * risk_params.get("max_position_pct", 0.15)
                    max_qty = int(max_pos_val / buy_price)
                    quantity = min(quantity, max_qty)

                    cost = buy_price * quantity
                    commission = max(cost * self.commission_pct, self.commission_flat)

                    if quantity <= 0 or cost + commission > cash:
                        continue

                    positions[ticker] = {
                        "quantity": quantity,
                        "avg_cost": buy_price,
                        "stop_loss": stop,
                        "target": sig.get("target_price"),
                        "trailing_stop": buy_price * (1 - risk_params.get("trailing_stop_pct", 0.08)),
                    }
                    cash -= cost + commission
                    last_trade_date[ticker] = current_date

                    trade_log.append({
                        "date": date_str, "action": "BUY", "ticker": ticker,
                        "quantity": quantity, "price": buy_price,
                        "pnl": 0, "pnl_pct": 0,
                        "reason": "signal_buy", "commission": commission,
                    })

            # --- Record Daily Equity ---
            invested_value = sum(
                price_map.get(t, p["avg_cost"]) * p["quantity"]
                for t, p in positions.items()
            )
            total_value = cash + invested_value

            equity_curve.append({
                "date": date_str,
                "total_value": total_value,
                "cash": cash,
                "invested": invested_value,
                "num_positions": len(positions),
            })

        # ------------------------------------------------------------------
        # Compute Results
        # ------------------------------------------------------------------
        equity_df = pd.DataFrame(equity_curve)
        equity_df["date"] = pd.to_datetime(equity_df["date"])
        equity_df = equity_df.set_index("date")
        equity_df["returns"] = equity_df["total_value"].pct_change()

        trades_df = pd.DataFrame(trade_log)

        # Benchmark
        bench_prices = all_prices[all_prices["ticker"] == self.benchmark_ticker].sort_values("date")
        bench_prices = bench_prices.set_index("date")["close"]
        bench_returns = bench_prices.pct_change().dropna()

        # Calculate metrics
        portfolio_returns = equity_df["returns"].dropna()
        metrics = self.risk_calc.calculate_all(
            portfolio_returns, bench_returns, trades_df
        )

        bench_metrics = self.risk_calc.calculate_all(bench_returns)

        logger.info(f"\n{'=' * 60}")
        logger.info(f"BACKTEST RESULTS: {fund_cfg['name']}")
        logger.info(f"{'=' * 60}")
        logger.info(f"Total Return: {metrics['total_return']:.2%}")
        logger.info(f"Annual Return: {metrics['annual_return']:.2%}")
        logger.info(f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
        logger.info(f"Max Drawdown: {metrics['max_drawdown']:.2%}")
        logger.info(f"Win Rate: {metrics.get('win_rate', 0):.1%}")
        logger.info(f"Profit Factor: {metrics.get('profit_factor', 0):.2f}")
        logger.info(f"Total Trades: {metrics.get('total_trades', 0)}")
        logger.info(f"\nBenchmark ({self.benchmark_ticker}):")
        logger.info(f"  Total Return: {bench_metrics['total_return']:.2%}")
        logger.info(f"  Sharpe Ratio: {bench_metrics['sharpe_ratio']:.2f}")

        # Save results
        result = {
            "fund": fund_name,
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": initial_capital,
            "final_value": float(equity_df["total_value"].iloc[-1]),
            "equity_curve": equity_df.reset_index(),
            "trade_log": trades_df,
            "metrics": metrics,
            "benchmark_metrics": bench_metrics,
        }

        self._save_backtest_results(fund_name, result)

        return result

    # ------------------------------------------------------------------
    # Save / Load
    # ------------------------------------------------------------------
    def _save_backtest_results(self, fund_name: str, results: Dict):
        """Save backtest results to Parquet."""
        # Equity curve
        if "equity_curve" in results:
            save_parquet(
                results["equity_curve"], "backtest",
                f"equity_{fund_name}"
            )

        # Trade log
        if "trade_log" in results and not results["trade_log"].empty:
            save_parquet(
                results["trade_log"], "backtest",
                f"trades_{fund_name}"
            )

        # Summary metrics
        summary = {k: v for k, v in results["metrics"].items()
                    if not isinstance(v, (dict, list, pd.DataFrame))}
        summary["fund"] = fund_name
        summary["start_date"] = results["start_date"]
        summary["end_date"] = results["end_date"]
        summary["initial_capital"] = results["initial_capital"]
        summary["final_value"] = results["final_value"]

        summary_df = pd.DataFrame([summary])
        save_parquet(summary_df, "backtest", f"summary_{fund_name}")

        logger.info(f"Backtest results saved for {fund_name}")

    def load_backtest_results(self, fund_name: str) -> Optional[Dict]:
        """Load saved backtest results."""
        equity = load_parquet("backtest", f"equity_{fund_name}")
        trades = load_parquet("backtest", f"trades_{fund_name}")
        summary = load_parquet("backtest", f"summary_{fund_name}")

        if equity is None:
            return None

        return {
            "equity_curve": equity,
            "trade_log": trades if trades is not None else pd.DataFrame(),
            "summary": summary.iloc[0].to_dict() if summary is not None else {},
        }

    # ------------------------------------------------------------------
    # Run All Funds
    # ------------------------------------------------------------------
    def run_all_backtests(self, **kwargs) -> Dict[str, Dict]:
        """Run backtests for all configured funds."""
        results = {}
        for fund_name in self.config.get("funds", {}):
            results[fund_name] = self.run_backtest(fund_name, **kwargs)
        return results
