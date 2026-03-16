"""
Paper Trading Portfolio Manager.

Manages hypothetical trades independently from the real portfolio.
Each strategy fund has its own paper portfolio for tracking performance.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any

import numpy as np
import pandas as pd
from loguru import logger

from src.utils import (
    load_config, get_fund_config, save_parquet, load_parquet,
    append_parquet, trading_date_str, get_sector,
)


class PaperPortfolio:
    """
    Manages a paper trading portfolio for a single strategy fund.
    Tracks positions, trades, cash balance, and performance.
    """

    def __init__(self, fund_name: str):
        self.fund_name = fund_name
        self.fund_config = get_fund_config(fund_name)
        self.risk_params = self.fund_config.get("risk_params", {})
        self.starting_capital = self.fund_config.get("starting_capital", 100000)

        # Load existing state or initialize
        self.positions = self._load_positions()
        self.trades = self._load_trades()
        self.balance = self._load_balance()

        if self.balance is None:
            self.balance = {
                "cash": self.starting_capital,
                "total_value": self.starting_capital,
                "last_updated": datetime.now().isoformat(),
            }
            self._save_balance()

    # ------------------------------------------------------------------
    # Position Management
    # ------------------------------------------------------------------
    def get_positions(self) -> pd.DataFrame:
        """Return current positions DataFrame."""
        if self.positions is None or self.positions.empty:
            return pd.DataFrame(columns=[
                "ticker", "quantity", "avg_cost", "current_price",
                "market_value", "unrealized_pnl", "unrealized_pnl_pct",
                "stop_loss_price", "trailing_stop_price", "target_price",
                "entry_date", "sector",
            ])
        return self.positions.copy()

    def get_position(self, ticker: str) -> Optional[Dict]:
        """Get a single position."""
        if self.positions is None or self.positions.empty:
            return None
        mask = self.positions["ticker"] == ticker
        if mask.any():
            return self.positions[mask].iloc[0].to_dict()
        return None

    def execute_buy(
        self,
        ticker: str,
        price: float,
        quantity: Optional[int] = None,
        stop_loss_price: Optional[float] = None,
        target_price: Optional[float] = None,
        signal_confidence: float = 0.5,
        reason: str = "",
    ) -> bool:
        """
        Execute a paper buy order.
        If quantity not specified, uses position sizing based on risk params.
        """
        if quantity is None:
            quantity = self._calculate_position_size(ticker, price, stop_loss_price)

        if quantity <= 0:
            logger.warning(f"[{self.fund_name}] Position size 0 for {ticker}, skipping")
            return False

        cost = price * quantity

        # Check cash
        if cost > self.balance["cash"]:
            logger.warning(
                f"[{self.fund_name}] Insufficient cash for {ticker}: "
                f"need ${cost:,.2f}, have ${self.balance['cash']:,.2f}"
            )
            return False

        # Check position size limit
        max_position_pct = self.risk_params.get("max_position_pct", 0.15)
        if cost / self.balance["total_value"] > max_position_pct:
            max_cost = self.balance["total_value"] * max_position_pct
            quantity = int(max_cost / price)
            cost = price * quantity
            if quantity <= 0:
                return False

        # Check sector concentration
        if not self._check_sector_limit(ticker, cost):
            logger.warning(f"[{self.fund_name}] Sector limit exceeded for {ticker}")
            return False

        # Default stop-loss
        if stop_loss_price is None:
            stop_loss_pct = self.risk_params.get("stop_loss_pct", 0.10)
            stop_loss_price = price * (1 - stop_loss_pct)

        trailing_stop_pct = self.risk_params.get("trailing_stop_pct", 0.08)
        trailing_stop = price * (1 - trailing_stop_pct)

        # Update or create position
        existing = self.get_position(ticker)
        if existing:
            # Average into position
            old_qty = existing["quantity"]
            old_cost = existing["avg_cost"]
            new_qty = old_qty + quantity
            new_avg = (old_cost * old_qty + price * quantity) / new_qty
            self._update_position(ticker, {
                "quantity": new_qty,
                "avg_cost": new_avg,
                "stop_loss_price": stop_loss_price,
                "trailing_stop_price": max(trailing_stop, existing.get("trailing_stop_price", 0)),
                "target_price": target_price or existing.get("target_price"),
            })
        else:
            new_pos = pd.DataFrame([{
                "ticker": ticker,
                "quantity": quantity,
                "avg_cost": price,
                "current_price": price,
                "market_value": cost,
                "unrealized_pnl": 0.0,
                "unrealized_pnl_pct": 0.0,
                "stop_loss_price": stop_loss_price,
                "trailing_stop_price": trailing_stop,
                "target_price": target_price,
                "entry_date": datetime.now().isoformat(),
                "sector": get_sector(ticker),
            }])
            if self.positions is None or self.positions.empty:
                self.positions = new_pos
            else:
                self.positions = pd.concat([self.positions, new_pos], ignore_index=True)

        # Deduct cash
        self.balance["cash"] -= cost
        self._record_trade("BUY", ticker, quantity, price, stop_loss_price,
                           target_price, signal_confidence, reason)
        self._save_all()

        logger.info(
            f"[{self.fund_name}] BUY {quantity} {ticker} @ ${price:.2f} "
            f"(${cost:,.2f}) | SL: ${stop_loss_price:.2f}"
        )
        return True

    def execute_sell(
        self,
        ticker: str,
        price: float,
        quantity: Optional[int] = None,
        reason: str = "",
        signal_confidence: float = 0.5,
    ) -> bool:
        """Execute a paper sell order."""
        position = self.get_position(ticker)
        if not position:
            logger.warning(f"[{self.fund_name}] No position in {ticker} to sell")
            return False

        if quantity is None:
            quantity = position["quantity"]
        quantity = min(quantity, position["quantity"])

        proceeds = price * quantity
        pnl = (price - position["avg_cost"]) * quantity
        pnl_pct = (price / position["avg_cost"]) - 1

        # Update position
        remaining = position["quantity"] - quantity
        if remaining <= 0:
            # Close entire position
            self.positions = self.positions[self.positions["ticker"] != ticker]
        else:
            self._update_position(ticker, {"quantity": remaining})

        # Add cash
        self.balance["cash"] += proceeds
        self._record_trade("SELL", ticker, quantity, price, None, None,
                           signal_confidence, reason, pnl, pnl_pct)
        self._save_all()

        logger.info(
            f"[{self.fund_name}] SELL {quantity} {ticker} @ ${price:.2f} "
            f"(${proceeds:,.2f}) | PnL: ${pnl:,.2f} ({pnl_pct:.1%})"
        )
        return True

    def update_prices(self, price_data: Dict[str, float]):
        """
        Update current prices for all positions and check stop-losses.
        price_data: {ticker: current_price}
        """
        if self.positions is None or self.positions.empty:
            return

        triggered_stops = []

        for idx, pos in self.positions.iterrows():
            ticker = pos["ticker"]
            if ticker not in price_data:
                continue

            current = price_data[ticker]
            avg_cost = pos["avg_cost"]
            quantity = pos["quantity"]

            self.positions.at[idx, "current_price"] = current
            self.positions.at[idx, "market_value"] = current * quantity
            self.positions.at[idx, "unrealized_pnl"] = (current - avg_cost) * quantity
            self.positions.at[idx, "unrealized_pnl_pct"] = (current / avg_cost) - 1

            # Update trailing stop (only moves up)
            trailing_pct = self.risk_params.get("trailing_stop_pct", 0.08)
            new_trailing = current * (1 - trailing_pct)
            old_trailing = pos.get("trailing_stop_price", 0) or 0
            if new_trailing > old_trailing:
                self.positions.at[idx, "trailing_stop_price"] = new_trailing

            # Check stop-loss triggers
            stop_loss = pos.get("stop_loss_price", 0) or 0
            trailing_stop = self.positions.at[idx, "trailing_stop_price"] or 0
            effective_stop = max(stop_loss, trailing_stop)

            if current <= effective_stop and effective_stop > 0:
                triggered_stops.append((ticker, current, "stop_loss"))

            # Check take-profit
            target = pos.get("target_price")
            if target and current >= target:
                triggered_stops.append((ticker, current, "take_profit"))

        # Execute triggered stops
        for ticker, price, reason in triggered_stops:
            self.execute_sell(ticker, price, reason=f"Auto: {reason}")

        # Update total portfolio value
        invested = 0
        if not self.positions.empty:
            invested = self.positions["market_value"].sum()
        self.balance["total_value"] = self.balance["cash"] + invested
        self.balance["last_updated"] = datetime.now().isoformat()

        self._save_all()

    # ------------------------------------------------------------------
    # Position Sizing
    # ------------------------------------------------------------------
    def _calculate_position_size(
        self, ticker: str, price: float, stop_loss_price: Optional[float] = None
    ) -> int:
        """
        Calculate position size based on risk parameters.
        Uses fixed fractional risk (2% of portfolio per trade).
        Optionally uses Kelly Criterion.
        """
        total_value = self.balance["total_value"]
        max_risk_pct = self.risk_params.get("max_risk_per_trade", 0.02)
        risk_amount = total_value * max_risk_pct

        if stop_loss_price and stop_loss_price < price:
            risk_per_share = price - stop_loss_price
        else:
            stop_pct = self.risk_params.get("stop_loss_pct", 0.10)
            risk_per_share = price * stop_pct

        if risk_per_share <= 0:
            return 0

        quantity = int(risk_amount / risk_per_share)

        # Kelly Criterion adjustment
        if self.risk_params.get("use_kelly_criterion", False):
            win_rate = self._calculate_win_rate()
            if win_rate > 0:
                avg_win, avg_loss = self._calculate_avg_win_loss()
                if avg_loss > 0:
                    kelly = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
                    kelly_fraction = self.risk_params.get("kelly_fraction", 0.25)
                    kelly_adjusted = max(0, kelly * kelly_fraction)
                    kelly_qty = int((total_value * kelly_adjusted) / price)
                    quantity = min(quantity, kelly_qty)

        # Cap by max position size
        max_pos_pct = self.risk_params.get("max_position_pct", 0.15)
        max_qty = int((total_value * max_pos_pct) / price)
        quantity = min(quantity, max_qty)

        return max(0, quantity)

    def _check_sector_limit(self, ticker: str, additional_cost: float) -> bool:
        """Check if adding to this sector would exceed limits."""
        sector = get_sector(ticker)
        if sector == "Unknown":
            return True

        max_sector_pct = self.risk_params.get("max_sector_pct", 0.40)
        total_value = self.balance["total_value"]

        current_sector_value = 0
        if self.positions is not None and not self.positions.empty:
            sector_positions = self.positions[self.positions["sector"] == sector]
            current_sector_value = sector_positions["market_value"].sum()

        return (current_sector_value + additional_cost) / total_value <= max_sector_pct

    def _calculate_win_rate(self) -> float:
        """Calculate historical win rate from closed trades."""
        if self.trades is None or self.trades.empty:
            return 0.5
        sells = self.trades[self.trades["action"] == "SELL"]
        if sells.empty:
            return 0.5
        wins = sells[sells["pnl"] > 0]
        return len(wins) / len(sells)

    def _calculate_avg_win_loss(self):
        """Calculate average win and average loss amounts."""
        if self.trades is None or self.trades.empty:
            return 1.0, 1.0
        sells = self.trades[self.trades["action"] == "SELL"]
        wins = sells[sells["pnl"] > 0]["pnl"]
        losses = sells[sells["pnl"] <= 0]["pnl"].abs()
        avg_win = wins.mean() if not wins.empty else 1.0
        avg_loss = losses.mean() if not losses.empty else 1.0
        return avg_win, avg_loss

    # ------------------------------------------------------------------
    # Trade Recording
    # ------------------------------------------------------------------
    def _record_trade(
        self, action, ticker, quantity, price,
        stop_loss=None, target=None, confidence=0.5,
        reason="", pnl=None, pnl_pct=None,
    ):
        """Record a trade to the trade log."""
        trade = pd.DataFrame([{
            "fund": self.fund_name,
            "datetime": datetime.now().isoformat(),
            "date": trading_date_str(),
            "action": action,
            "ticker": ticker,
            "quantity": quantity,
            "price": price,
            "value": price * quantity,
            "stop_loss_price": stop_loss,
            "target_price": target,
            "confidence": confidence,
            "reason": reason,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
        }])

        if self.trades is None or self.trades.empty:
            self.trades = trade
        else:
            self.trades = pd.concat([self.trades, trade], ignore_index=True)

    def _update_position(self, ticker: str, updates: Dict):
        """Update fields in an existing position."""
        mask = self.positions["ticker"] == ticker
        for key, value in updates.items():
            self.positions.loc[mask, key] = value

    # ------------------------------------------------------------------
    # Performance Metrics
    # ------------------------------------------------------------------
    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get summary of portfolio state."""
        positions = self.get_positions()
        total_value = self.balance["total_value"]
        cash = self.balance["cash"]

        invested = total_value - cash
        returns = (total_value / self.starting_capital) - 1

        summary = {
            "fund": self.fund_name,
            "total_value": total_value,
            "cash": cash,
            "invested": invested,
            "cash_pct": cash / total_value if total_value > 0 else 1.0,
            "num_positions": len(positions),
            "total_return": returns,
            "starting_capital": self.starting_capital,
        }

        if not positions.empty:
            summary["total_unrealized_pnl"] = positions["unrealized_pnl"].sum()
            summary["best_position"] = positions.loc[
                positions["unrealized_pnl_pct"].idxmax(), "ticker"
            ] if not positions.empty else None
            summary["worst_position"] = positions.loc[
                positions["unrealized_pnl_pct"].idxmin(), "ticker"
            ] if not positions.empty else None

        return summary

    def get_daily_values(self) -> Optional[pd.DataFrame]:
        """Load daily portfolio value history."""
        return load_parquet("portfolios", f"daily_values_{self.fund_name}")

    def record_daily_value(self):
        """Record today's portfolio value for equity curve tracking."""
        row = pd.DataFrame([{
            "fund": self.fund_name,
            "date": trading_date_str(),
            "total_value": self.balance["total_value"],
            "cash": self.balance["cash"],
            "invested": self.balance["total_value"] - self.balance["cash"],
            "num_positions": len(self.get_positions()),
        }])
        append_parquet(row, "portfolios", f"daily_values_{self.fund_name}")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load_positions(self) -> Optional[pd.DataFrame]:
        return load_parquet("portfolios", f"positions_{self.fund_name}")

    def _load_trades(self) -> Optional[pd.DataFrame]:
        return load_parquet("portfolios", f"trades_{self.fund_name}")

    def _load_balance(self) -> Optional[Dict]:
        df = load_parquet("portfolios", f"balance_{self.fund_name}")
        if df is not None and not df.empty:
            return df.iloc[-1].to_dict()
        return None

    def _save_balance(self):
        bal_df = pd.DataFrame([self.balance])
        save_parquet(bal_df, "portfolios", f"balance_{self.fund_name}")

    def _save_all(self):
        if self.positions is not None and not self.positions.empty:
            save_parquet(self.positions, "portfolios", f"positions_{self.fund_name}")
        self._save_balance()
        if self.trades is not None and not self.trades.empty:
            save_parquet(self.trades, "portfolios", f"trades_{self.fund_name}")


class PaperPortfolioManager:
    """Manages paper portfolios for all strategy funds."""

    def __init__(self):
        config = load_config()
        self.fund_names = list(config.get("funds", {}).keys())
        self.portfolios: Dict[str, PaperPortfolio] = {}

        for name in self.fund_names:
            self.portfolios[name] = PaperPortfolio(name)
            logger.debug(f"Loaded paper portfolio: {name}")

    def get_portfolio(self, fund_name: str) -> PaperPortfolio:
        """Get a specific fund's paper portfolio."""
        if fund_name not in self.portfolios:
            raise ValueError(f"Unknown fund: {fund_name}")
        return self.portfolios[fund_name]

    def update_all_prices(self, price_data: Dict[str, float]):
        """Update prices across all fund portfolios."""
        for name, portfolio in self.portfolios.items():
            portfolio.update_prices(price_data)

    def record_all_daily_values(self):
        """Record daily value snapshots for all funds."""
        for portfolio in self.portfolios.values():
            portfolio.record_daily_value()

    def get_all_summaries(self) -> List[Dict]:
        """Get portfolio summaries for all funds."""
        return [p.get_portfolio_summary() for p in self.portfolios.values()]
