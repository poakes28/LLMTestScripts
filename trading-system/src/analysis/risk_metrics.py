"""
Risk Metrics Calculator.

Computes portfolio-level and individual-stock risk metrics:
Sharpe, Sortino, Calmar, max drawdown, alpha, beta, VaR, win rate, profit factor.
"""

from typing import Optional, Dict, Any, List

import numpy as np
import pandas as pd
from scipy import stats
from loguru import logger

from src.utils import load_config


class RiskMetrics:
    """Calculate comprehensive risk and performance metrics."""

    def __init__(self):
        config = load_config()
        bt = config.get("backtest", {})
        self.risk_free_rate = bt.get("risk_free_rate", 0.05)
        self.trading_days = 252

    # ------------------------------------------------------------------
    # Core Performance Metrics
    # ------------------------------------------------------------------
    def calculate_all(
        self,
        returns: pd.Series,
        benchmark_returns: Optional[pd.Series] = None,
        trades: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """
        Calculate all risk and performance metrics.

        Args:
            returns: Series of daily portfolio returns
            benchmark_returns: Series of benchmark daily returns (SPY)
            trades: DataFrame of trades with 'pnl' column for win-rate stats
        """
        returns = returns.dropna()
        if len(returns) < 10:
            logger.warning("Insufficient returns data for metrics")
            return self._empty_metrics()

        metrics = {}

        # Basic returns
        total_return = (1 + returns).prod() - 1
        annual_return = (1 + total_return) ** (self.trading_days / len(returns)) - 1
        annual_vol = returns.std() * np.sqrt(self.trading_days)

        metrics["total_return"] = round(total_return, 4)
        metrics["annual_return"] = round(annual_return, 4)
        metrics["annual_volatility"] = round(annual_vol, 4)
        metrics["daily_vol"] = round(returns.std(), 6)

        # Sharpe Ratio
        excess = returns.mean() - self.risk_free_rate / self.trading_days
        metrics["sharpe_ratio"] = round(
            excess / returns.std() * np.sqrt(self.trading_days) if returns.std() > 0 else 0, 3
        )

        # Sortino Ratio (only downside deviation)
        downside = returns[returns < 0]
        downside_std = downside.std() if len(downside) > 1 else returns.std()
        metrics["sortino_ratio"] = round(
            excess / downside_std * np.sqrt(self.trading_days) if downside_std > 0 else 0, 3
        )

        # Max Drawdown
        cumulative = (1 + returns).cumprod()
        rolling_max = cumulative.expanding().max()
        drawdowns = cumulative / rolling_max - 1
        max_dd = drawdowns.min()
        metrics["max_drawdown"] = round(max_dd, 4)
        metrics["max_drawdown_duration"] = self._max_drawdown_duration(drawdowns)

        # Calmar Ratio
        metrics["calmar_ratio"] = round(
            annual_return / abs(max_dd) if max_dd != 0 else 0, 3
        )

        # VaR (Value at Risk) - 95% and 99%
        metrics["var_95"] = round(np.percentile(returns, 5), 4)
        metrics["var_99"] = round(np.percentile(returns, 1), 4)

        # CVaR (Conditional VaR / Expected Shortfall)
        var_95_val = np.percentile(returns, 5)
        metrics["cvar_95"] = round(returns[returns <= var_95_val].mean(), 4) if len(returns[returns <= var_95_val]) > 0 else 0

        # Best/Worst days
        metrics["best_day"] = round(returns.max(), 4)
        metrics["worst_day"] = round(returns.min(), 4)
        metrics["positive_days_pct"] = round((returns > 0).mean(), 3)

        # Alpha & Beta vs Benchmark
        if benchmark_returns is not None:
            bench = benchmark_returns.dropna()
            # Align dates
            common = returns.index.intersection(bench.index)
            if len(common) > 20:
                r = returns.loc[common]
                b = bench.loc[common]
                slope, intercept, r_val, p_val, std_err = stats.linregress(b, r)
                metrics["beta"] = round(slope, 3)
                metrics["alpha"] = round(intercept * self.trading_days, 4)
                metrics["r_squared"] = round(r_val ** 2, 3)
                metrics["correlation"] = round(r.corr(b), 3)
                metrics["tracking_error"] = round(
                    (r - b).std() * np.sqrt(self.trading_days), 4
                )
                metrics["information_ratio"] = round(
                    (r.mean() - b.mean()) / (r - b).std() * np.sqrt(self.trading_days)
                    if (r - b).std() > 0 else 0, 3
                )
            else:
                metrics.update({"beta": None, "alpha": None, "r_squared": None,
                                "correlation": None, "tracking_error": None,
                                "information_ratio": None})
        else:
            metrics.update({"beta": None, "alpha": None, "r_squared": None,
                            "correlation": None, "tracking_error": None,
                            "information_ratio": None})

        # Trade-based metrics
        if trades is not None and not trades.empty and "pnl" in trades.columns:
            sell_trades = trades[trades.get("action", trades.get("side", "")) == "SELL"] if "action" in trades.columns else trades
            if not sell_trades.empty and "pnl" in sell_trades.columns:
                pnl = sell_trades["pnl"].dropna()
                wins = pnl[pnl > 0]
                losses = pnl[pnl <= 0]

                metrics["total_trades"] = len(pnl)
                metrics["winning_trades"] = len(wins)
                metrics["losing_trades"] = len(losses)
                metrics["win_rate"] = round(len(wins) / len(pnl), 3) if len(pnl) > 0 else 0
                metrics["avg_win"] = round(wins.mean(), 2) if not wins.empty else 0
                metrics["avg_loss"] = round(losses.mean(), 2) if not losses.empty else 0
                metrics["profit_factor"] = round(
                    wins.sum() / abs(losses.sum()) if losses.sum() != 0 else float("inf"), 2
                )
                metrics["expectancy"] = round(pnl.mean(), 2)
                metrics["largest_win"] = round(wins.max(), 2) if not wins.empty else 0
                metrics["largest_loss"] = round(losses.min(), 2) if not losses.empty else 0
            else:
                metrics.update(self._empty_trade_metrics())
        else:
            metrics.update(self._empty_trade_metrics())

        return metrics

    # ------------------------------------------------------------------
    # Drawdown Analysis
    # ------------------------------------------------------------------
    @staticmethod
    def _max_drawdown_duration(drawdowns: pd.Series) -> int:
        """Calculate the longest drawdown duration in days."""
        in_drawdown = drawdowns < 0
        if not in_drawdown.any():
            return 0

        # Find consecutive drawdown periods
        groups = (~in_drawdown).cumsum()
        dd_groups = groups[in_drawdown]
        if dd_groups.empty:
            return 0

        durations = dd_groups.groupby(dd_groups).count()
        return int(durations.max())

    def calculate_drawdown_series(self, returns: pd.Series) -> pd.DataFrame:
        """Calculate full drawdown time series."""
        cumulative = (1 + returns).cumprod()
        rolling_max = cumulative.expanding().max()
        drawdown = cumulative / rolling_max - 1

        return pd.DataFrame({
            "cumulative_return": cumulative,
            "rolling_max": rolling_max,
            "drawdown": drawdown,
        })

    # ------------------------------------------------------------------
    # Rolling Metrics
    # ------------------------------------------------------------------
    def rolling_sharpe(self, returns: pd.Series, window: int = 63) -> pd.Series:
        """Calculate rolling Sharpe ratio (default 3-month window)."""
        rf_daily = self.risk_free_rate / self.trading_days
        excess = returns - rf_daily
        rolling = excess.rolling(window)
        return (rolling.mean() / rolling.std()) * np.sqrt(self.trading_days)

    def rolling_volatility(self, returns: pd.Series, window: int = 21) -> pd.Series:
        """Calculate rolling annualized volatility."""
        return returns.rolling(window).std() * np.sqrt(self.trading_days)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _empty_metrics() -> Dict:
        return {
            "total_return": 0, "annual_return": 0, "annual_volatility": 0,
            "sharpe_ratio": 0, "sortino_ratio": 0, "max_drawdown": 0,
            "calmar_ratio": 0, "var_95": 0, "var_99": 0, "cvar_95": 0,
            "beta": None, "alpha": None, "win_rate": 0, "profit_factor": 0,
        }

    @staticmethod
    def _empty_trade_metrics() -> Dict:
        return {
            "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
            "win_rate": 0, "avg_win": 0, "avg_loss": 0, "profit_factor": 0,
            "expectancy": 0, "largest_win": 0, "largest_loss": 0,
        }
