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
    # Screen Backtest — equal-weight portfolio of screened stocks
    # ------------------------------------------------------------------
    def run_screen_backtest(
        self,
        tickers: List[str],
        start_date: str,
        end_date: str,
        initial_capital: float,
        hold_mode: str = "fixed",
        hold_period_days: int = 30,
        exit_criteria: Optional[Dict] = None,
        benchmark: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Backtest an equal-weight portfolio of screened stocks.

        Args:
            tickers:          List of ticker symbols from the screener
            start_date:       Entry date (YYYY-MM-DD)
            end_date:         Latest allowed exit date (YYYY-MM-DD)
            initial_capital:  Starting portfolio value
            hold_mode:        "fixed" — sell after hold_period_days
                              "criteria_exit" — sell on technical SELL signal
            hold_period_days: Days to hold before forced exit (fixed mode)
            exit_criteria:    Optional dict; currently unused for local backtesting
                              (technical signal-based exit only in criteria_exit mode)
            benchmark:        Benchmark ticker (default: SPY)

        Returns:
            dict with equity_curve, individual_returns, metrics,
            benchmark_metrics, survivorship_bias_note, warnings
        """
        import yfinance as yf

        benchmark = benchmark or self.benchmark_ticker
        warnings: List[str] = []

        if not tickers:
            return {"error": "No tickers provided"}

        logger.info(
            f"Screen backtest: {len(tickers)} tickers | {start_date} → {end_date} "
            f"| mode={hold_mode} | capital=${initial_capital:,.0f}"
        )

        # ----------------------------------------------------------------
        # 1. Download price history for tickers + benchmark
        # ----------------------------------------------------------------
        all_tickers = list(dict.fromkeys(tickers + [benchmark]))  # preserve order, dedup
        try:
            raw = yf.download(
                all_tickers,
                start=start_date,
                end=end_date,
                interval="1d",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
        except Exception as e:
            return {"error": f"Price download failed: {e}"}

        if raw.empty:
            return {"error": "No price data returned by yfinance"}

        # Normalise to a dict: ticker → pd.Series (date-indexed close prices)
        def _get_close(ticker: str) -> Optional[pd.Series]:
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    return raw["Close"][ticker].dropna()
                else:
                    return raw["Close"].dropna()
            except Exception:
                return None

        price_map: Dict[str, pd.Series] = {}
        missing: List[str] = []
        for t in all_tickers:
            s = _get_close(t)
            if s is not None and len(s) >= 5:
                price_map[t] = s
            else:
                missing.append(t)

        if missing:
            warnings.append(f"No price data for: {', '.join(missing)}")

        # Active tickers = those with price data (excluding benchmark)
        active_tickers = [t for t in tickers if t in price_map]
        if not active_tickers:
            return {"error": "No price data available for any of the provided tickers"}

        # ----------------------------------------------------------------
        # 2. Determine entry date (first trading day >= start_date)
        # ----------------------------------------------------------------
        all_dates = sorted(
            set().union(*[s.index for s in price_map.values()])
        )
        start_dt = pd.Timestamp(start_date)
        end_dt = pd.Timestamp(end_date)

        trading_dates = [d for d in all_dates if start_dt <= d <= end_dt]
        if not trading_dates:
            return {"error": "No trading days in specified date range"}

        entry_date = trading_dates[0]

        # ----------------------------------------------------------------
        # 3. Entry prices — equal-weight allocation
        # ----------------------------------------------------------------
        entry_prices: Dict[str, float] = {}
        for t in active_tickers:
            s = price_map[t]
            avail = s[s.index >= entry_date]
            if avail.empty:
                warnings.append(f"{t}: no price on or after entry date, skipped")
                continue
            entry_prices[t] = float(avail.iloc[0])

        investable = list(entry_prices.keys())
        if not investable:
            return {"error": "No tickers have prices on the entry date"}

        position_value = initial_capital / len(investable)
        positions: Dict[str, Dict] = {}
        for t in investable:
            ep = entry_prices[t]
            buy_price = ep * (1 + self.slippage_pct)
            commission = max(position_value * self.commission_pct, self.commission_flat)
            shares = (position_value - commission) / buy_price
            positions[t] = {
                "entry_date": entry_date,
                "entry_price": buy_price,
                "shares": shares,
                "commission_in": commission,
            }

        cash = initial_capital - sum(
            p["shares"] * p["entry_price"] + p["commission_in"]
            for p in positions.values()
        )

        # ----------------------------------------------------------------
        # 4. Pre-compute OHLCV DataFrames for criteria_exit mode
        # ----------------------------------------------------------------
        def _build_ohlcv(ticker: str) -> Optional[pd.DataFrame]:
            """Build a full OHLCV DataFrame suitable for TechnicalAnalyzer."""
            try:
                raw_full = yf.download(
                    ticker,
                    start=(start_dt - pd.Timedelta(days=200)).strftime("%Y-%m-%d"),
                    end=end_date,
                    interval="1d",
                    auto_adjust=True,
                    progress=False,
                )
                if raw_full.empty:
                    return None
                df = raw_full.reset_index()
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = [c[0] if c[1] == "" else c[0] for c in df.columns]
                df = df.rename(columns={
                    "Date": "date", "Open": "open", "High": "high",
                    "Low": "low", "Close": "close", "Volume": "volume",
                })
                df["ticker"] = ticker
                return df.dropna(subset=["close"])
            except Exception:
                return None

        ohlcv_cache: Dict[str, Optional[pd.DataFrame]] = {}
        if hold_mode == "criteria_exit":
            logger.info("Fetching full OHLCV for criteria_exit mode...")
            for t in list(positions.keys()):
                ohlcv_cache[t] = _build_ohlcv(t)

        # ----------------------------------------------------------------
        # 5. Daily simulation loop
        # ----------------------------------------------------------------
        exit_log: Dict[str, Dict] = {}  # ticker → exit info
        equity_curve = []
        fixed_exit_date = entry_date + pd.Timedelta(days=hold_period_days)
        check_interval = 5  # re-evaluate signals every N trading days
        day_counter = 0

        for current_date in trading_dates:
            day_counter += 1
            open_tickers = set(positions.keys()) - set(exit_log.keys())

            # --- criteria_exit: check signals every check_interval days ---
            if hold_mode == "criteria_exit" and day_counter % check_interval == 0:
                for t in list(open_tickers):
                    df = ohlcv_cache.get(t)
                    if df is None:
                        continue
                    hist = df[df["date"] <= current_date]
                    if len(hist) < 30:
                        continue
                    try:
                        hist_ind = self.technical.calculate_indicators(hist)
                        sig = self.technical.generate_signals(hist_ind)
                        if sig.get("signal") == "SELL":
                            exit_series = price_map[t]
                            avail = exit_series[exit_series.index >= current_date]
                            if avail.empty:
                                continue
                            sell_price = float(avail.iloc[0]) * (1 - self.slippage_pct)
                            pos = positions[t]
                            commission_out = max(
                                sell_price * pos["shares"] * self.commission_pct,
                                self.commission_flat,
                            )
                            proceeds = sell_price * pos["shares"] - commission_out
                            cash += proceeds
                            entry_dt = pos["entry_date"]
                            hold_days = (current_date - entry_dt).days
                            ret = sell_price / pos["entry_price"] - 1
                            exit_log[t] = {
                                "exit_date": current_date, "exit_price": sell_price,
                                "return_pct": ret, "hold_days": hold_days,
                                "exit_reason": "signal_sell",
                            }
                    except Exception as e:
                        logger.debug(f"Signal error for {t}: {e}")

            # --- fixed mode: close all on fixed_exit_date ---
            if hold_mode == "fixed" and current_date >= fixed_exit_date:
                for t in list(open_tickers):
                    exit_series = price_map[t]
                    avail = exit_series[exit_series.index >= current_date]
                    if avail.empty:
                        continue
                    sell_price = float(avail.iloc[0]) * (1 - self.slippage_pct)
                    pos = positions[t]
                    commission_out = max(
                        sell_price * pos["shares"] * self.commission_pct,
                        self.commission_flat,
                    )
                    proceeds = sell_price * pos["shares"] - commission_out
                    cash += proceeds
                    entry_dt = pos["entry_date"]
                    hold_days = (current_date - entry_dt).days
                    ret = sell_price / pos["entry_price"] - 1
                    exit_log[t] = {
                        "exit_date": current_date, "exit_price": sell_price,
                        "return_pct": ret, "hold_days": hold_days,
                        "exit_reason": "fixed_hold",
                    }
                if len(exit_log) == len(positions):
                    break  # all positions closed, stop looping

            # --- Mark-to-market equity ---
            open_tickers = set(positions.keys()) - set(exit_log.keys())
            invested = 0.0
            for t in open_tickers:
                series = price_map[t]
                avail = series[series.index <= current_date]
                if not avail.empty:
                    invested += float(avail.iloc[-1]) * positions[t]["shares"]

            equity_curve.append({
                "date": current_date.strftime("%Y-%m-%d"),
                "total_value": round(cash + invested, 2),
                "cash": round(cash, 2),
                "invested": round(invested, 2),
            })

        # Close any still-open positions at last available price
        for t in set(positions.keys()) - set(exit_log.keys()):
            series = price_map[t]
            if series.empty:
                continue
            sell_price = float(series.iloc[-1]) * (1 - self.slippage_pct)
            pos = positions[t]
            commission_out = max(
                sell_price * pos["shares"] * self.commission_pct,
                self.commission_flat,
            )
            cash += sell_price * pos["shares"] - commission_out
            entry_dt = pos["entry_date"]
            hold_days = (series.index[-1] - entry_dt).days
            ret = sell_price / pos["entry_price"] - 1
            exit_log[t] = {
                "exit_date": series.index[-1], "exit_price": sell_price,
                "return_pct": ret, "hold_days": hold_days,
                "exit_reason": "end_of_period",
            }

        # ----------------------------------------------------------------
        # 6. Compute metrics
        # ----------------------------------------------------------------
        eq_df = pd.DataFrame(equity_curve)
        if eq_df.empty:
            return {"error": "Empty equity curve"}

        eq_df["date"] = pd.to_datetime(eq_df["date"])
        eq_df = eq_df.set_index("date")
        portfolio_returns = eq_df["total_value"].pct_change().dropna()

        bench_returns = None
        bench_metrics = {}
        if benchmark in price_map:
            bench_series = price_map[benchmark]
            bench_in_range = bench_series[
                (bench_series.index >= entry_date) & (bench_series.index <= end_dt)
            ]
            bench_returns = bench_in_range.pct_change().dropna()
            bench_metrics = self.risk_calc.calculate_all(bench_returns)

        metrics = self.risk_calc.calculate_all(portfolio_returns, bench_returns)
        final_value = float(eq_df["total_value"].iloc[-1])

        # Individual returns list
        individual_returns = []
        for t, pos in positions.items():
            xi = exit_log.get(t, {})
            individual_returns.append({
                "ticker": t,
                "entry_date": pos["entry_date"].strftime("%Y-%m-%d"),
                "exit_date": xi.get("exit_date", end_dt).strftime("%Y-%m-%d")
                if hasattr(xi.get("exit_date", end_dt), "strftime")
                else str(xi.get("exit_date", end_dt)),
                "entry_price": round(pos["entry_price"], 4),
                "exit_price": round(xi.get("exit_price", pos["entry_price"]), 4),
                "return_pct": round(xi.get("return_pct", 0.0), 4),
                "hold_days": xi.get("hold_days", 0),
                "exit_reason": xi.get("exit_reason", "open"),
            })

        # Sort by return descending
        individual_returns.sort(key=lambda x: x["return_pct"], reverse=True)

        # ----------------------------------------------------------------
        # 7. Save summary
        # ----------------------------------------------------------------
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary_df = pd.DataFrame([{
            "tickers": ",".join(tickers),
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": initial_capital,
            "final_value": final_value,
            "hold_mode": hold_mode,
            "total_return": metrics.get("total_return"),
            "sharpe_ratio": metrics.get("sharpe_ratio"),
            "max_drawdown": metrics.get("max_drawdown"),
            "timestamp": timestamp,
        }])
        save_parquet(summary_df, "backtest", f"screen_backtest_{timestamp}")

        logger.info(
            f"Screen backtest complete: ${initial_capital:,.0f} → ${final_value:,.0f} "
            f"({metrics.get('total_return', 0):.2%})"
        )

        return {
            "tickers": tickers,
            "active_tickers": investable,
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": initial_capital,
            "final_value": round(final_value, 2),
            "hold_mode": hold_mode,
            "hold_period_days": hold_period_days if hold_mode == "fixed" else None,
            "equity_curve": equity_curve,
            "individual_returns": individual_returns,
            "metrics": metrics,
            "benchmark": benchmark,
            "benchmark_metrics": bench_metrics,
            "survivorship_bias_note": (
                "Fundamental metrics (P/E, ROE, margins) reflect current values only. "
                "yfinance does not provide historical fundamental data. "
                "Screener-based backtests therefore carry survivorship and look-ahead bias. "
                "Technical indicator backtesting is historically accurate."
            ),
            "warnings": warnings,
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
