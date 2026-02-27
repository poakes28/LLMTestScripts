"""
Technical Analysis Engine.

Calculates technical indicators, detects support/resistance levels,
and generates technical buy/sell signals with confidence scores.
"""

from typing import Optional, Dict, List, Tuple, Any

import numpy as np
import pandas as pd
import pandas_ta as ta
from loguru import logger

from src.utils import load_config


class TechnicalAnalyzer:
    """
    Computes technical indicators and generates signals.
    """

    def __init__(self, params: Optional[Dict] = None):
        config = load_config()
        self.defaults = config.get("technical_defaults", {})
        self.params = {**self.defaults, **(params or {})}

    # ------------------------------------------------------------------
    # Indicator Calculation
    # ------------------------------------------------------------------
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add all technical indicators to a price DataFrame.
        Input df must have columns: date, open, high, low, close, volume.
        Returns new DataFrame with indicator columns added.
        """
        df = df.copy().sort_values("date").reset_index(drop=True)

        if len(df) < 50:
            logger.warning("Insufficient data for full technical analysis")
            return df

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"].astype(float)

        # --- Moving Averages ---
        sma_s = self.params.get("sma_short", 20)
        sma_l = self.params.get("sma_long", 50)
        sma_t = self.params.get("sma_trend", 200)

        df["sma_short"] = ta.sma(close, length=sma_s)
        df["sma_long"] = ta.sma(close, length=sma_l)
        df["sma_trend"] = ta.sma(close, length=sma_t) if len(df) >= sma_t else np.nan
        df["ema_12"] = ta.ema(close, length=12)
        df["ema_26"] = ta.ema(close, length=26)

        # --- RSI ---
        rsi_period = self.params.get("rsi_period", 14)
        df["rsi"] = ta.rsi(close, length=rsi_period)

        # --- MACD ---
        macd_result = ta.macd(
            close,
            fast=self.params.get("macd_fast", 12),
            slow=self.params.get("macd_slow", 26),
            signal=self.params.get("macd_signal", 9),
        )
        if macd_result is not None:
            df["macd"] = macd_result.iloc[:, 0]
            df["macd_hist"] = macd_result.iloc[:, 1]
            df["macd_signal"] = macd_result.iloc[:, 2]

        # --- Bollinger Bands ---
        bb_period = self.params.get("bollinger_period", 20)
        bb_std = self.params.get("bollinger_std", 2.0)
        bbands = ta.bbands(close, length=bb_period, std=bb_std)
        if bbands is not None:
            df["bb_upper"] = bbands.iloc[:, 2]
            df["bb_middle"] = bbands.iloc[:, 1]
            df["bb_lower"] = bbands.iloc[:, 0]
            df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]
            df["bb_pct"] = (close - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])

        # --- ATR ---
        atr_period = self.params.get("atr_period", 14)
        df["atr"] = ta.atr(high, low, close, length=atr_period)
        df["atr_pct"] = df["atr"] / close

        # --- Volume ---
        vol_period = self.params.get("volume_avg_period", 20)
        df["volume_sma"] = ta.sma(volume, length=vol_period)
        df["volume_ratio"] = volume / df["volume_sma"]

        # --- Stochastic ---
        stoch = ta.stoch(high, low, close)
        if stoch is not None:
            df["stoch_k"] = stoch.iloc[:, 0]
            df["stoch_d"] = stoch.iloc[:, 1]

        # --- ADX ---
        adx_result = ta.adx(high, low, close)
        if adx_result is not None:
            df["adx"] = adx_result.iloc[:, 0]
            df["dmp"] = adx_result.iloc[:, 1]  # +DI
            df["dmn"] = adx_result.iloc[:, 2]  # -DI

        # --- OBV ---
        df["obv"] = ta.obv(close, volume)

        # --- Price vs Moving Averages ---
        df["above_sma_short"] = (close > df["sma_short"]).astype(int)
        df["above_sma_long"] = (close > df["sma_long"]).astype(int)
        df["above_sma_trend"] = (
            (close > df["sma_trend"]).astype(int)
            if "sma_trend" in df.columns and df["sma_trend"].notna().any()
            else 0
        )
        df["sma_cross"] = (df["sma_short"] > df["sma_long"]).astype(int)

        # --- Price momentum ---
        df["return_1d"] = close.pct_change(1)
        df["return_5d"] = close.pct_change(5)
        df["return_20d"] = close.pct_change(20)
        df["return_60d"] = close.pct_change(60) if len(df) >= 60 else np.nan

        return df

    # ------------------------------------------------------------------
    # Support and Resistance Detection
    # ------------------------------------------------------------------
    def find_support_resistance(
        self, df: pd.DataFrame, window: Optional[int] = None, touches: Optional[int] = None
    ) -> Dict[str, List[float]]:
        """
        Detect support and resistance levels using local min/max.
        Returns dict with 'support' and 'resistance' price levels.
        """
        if window is None:
            window = self.params.get("support_resistance_window", 20)
        if touches is None:
            touches = self.params.get("support_resistance_touches", 2)

        close = df["close"].values
        high = df["high"].values
        low = df["low"].values

        if len(close) < window * 2:
            return {"support": [], "resistance": []}

        # Find local minima (support) and maxima (resistance)
        supports = []
        resistances = []

        for i in range(window, len(close) - window):
            # Local minimum
            if low[i] == min(low[i - window : i + window + 1]):
                supports.append(low[i])
            # Local maximum
            if high[i] == max(high[i - window : i + window + 1]):
                resistances.append(high[i])

        # Cluster nearby levels (within 1.5%)
        support_levels = self._cluster_levels(supports, threshold=0.015)
        resistance_levels = self._cluster_levels(resistances, threshold=0.015)

        # Filter by minimum touches
        current_price = close[-1]
        support_levels = [s for s in support_levels if s < current_price]
        resistance_levels = [r for r in resistance_levels if r > current_price]

        # Sort: support descending (nearest first), resistance ascending
        support_levels.sort(reverse=True)
        resistance_levels.sort()

        return {
            "support": support_levels[:5],      # Top 5 nearest
            "resistance": resistance_levels[:5],
        }

    @staticmethod
    def _cluster_levels(levels: List[float], threshold: float = 0.015) -> List[float]:
        """Cluster nearby price levels together."""
        if not levels:
            return []

        levels = sorted(levels)
        clusters = [[levels[0]]]

        for level in levels[1:]:
            if (level - clusters[-1][-1]) / clusters[-1][-1] < threshold:
                clusters[-1].append(level)
            else:
                clusters.append([level])

        # Return average of each cluster (weighted by frequency)
        return [np.mean(c) for c in clusters if len(c) >= 1]

    # ------------------------------------------------------------------
    # Signal Generation
    # ------------------------------------------------------------------
    def generate_signals(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Generate technical trading signals with confidence scores.

        Returns dict with:
            signal: 'BUY', 'SELL', or 'HOLD'
            confidence: float 0-1
            reasons: list of contributing factors
            entry_price: suggested entry
            stop_loss: suggested stop-loss
            target_price: suggested target
            indicators: dict of current indicator values
        """
        if len(df) < 50:
            return self._empty_signal()

        # Ensure indicators are calculated
        if "rsi" not in df.columns:
            df = self.calculate_indicators(df)

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest

        score = 0.0  # Positive = bullish, Negative = bearish
        reasons = []
        max_score = 0.0

        # --- RSI Signal (weight: 2) ---
        rsi = latest.get("rsi")
        if pd.notna(rsi):
            max_score += 2
            oversold = self.params.get("rsi_oversold", 30)
            overbought = self.params.get("rsi_overbought", 70)
            if rsi < oversold:
                score += 2
                reasons.append(f"RSI oversold ({rsi:.1f})")
            elif rsi < 40:
                score += 1
                reasons.append(f"RSI approaching oversold ({rsi:.1f})")
            elif rsi > overbought:
                score -= 2
                reasons.append(f"RSI overbought ({rsi:.1f})")
            elif rsi > 60:
                score -= 1
                reasons.append(f"RSI approaching overbought ({rsi:.1f})")

        # --- MACD Signal (weight: 2) ---
        macd = latest.get("macd")
        macd_signal_val = latest.get("macd_signal")
        macd_hist = latest.get("macd_hist")
        prev_hist = prev.get("macd_hist")
        if pd.notna(macd) and pd.notna(macd_signal_val):
            max_score += 2
            if macd > macd_signal_val and (pd.notna(prev_hist) and prev_hist < 0 and macd_hist > 0):
                score += 2
                reasons.append("MACD bullish crossover")
            elif macd > macd_signal_val:
                score += 1
                reasons.append("MACD above signal line")
            elif macd < macd_signal_val and (pd.notna(prev_hist) and prev_hist > 0 and macd_hist < 0):
                score -= 2
                reasons.append("MACD bearish crossover")
            elif macd < macd_signal_val:
                score -= 1
                reasons.append("MACD below signal line")

        # --- Moving Average Trend (weight: 2) ---
        above_short = latest.get("above_sma_short", 0)
        above_long = latest.get("above_sma_long", 0)
        above_trend = latest.get("above_sma_trend", 0)
        sma_cross = latest.get("sma_cross", 0)
        prev_cross = prev.get("sma_cross", 0)
        max_score += 2
        if above_short and above_long and above_trend:
            score += 2
            reasons.append("Price above all major MAs (bullish trend)")
        elif above_short and above_long:
            score += 1
            reasons.append("Price above short and long MAs")
        elif not above_short and not above_long:
            score -= 2
            reasons.append("Price below short and long MAs (bearish trend)")
        # Golden/Death cross
        if sma_cross and not prev_cross:
            score += 1.5
            reasons.append("Golden cross (SMA short > SMA long)")
        elif not sma_cross and prev_cross:
            score -= 1.5
            reasons.append("Death cross (SMA short < SMA long)")

        # --- Bollinger Band Signal (weight: 1.5) ---
        bb_pct = latest.get("bb_pct")
        if pd.notna(bb_pct):
            max_score += 1.5
            if bb_pct < 0.05:
                score += 1.5
                reasons.append(f"Price at lower Bollinger Band ({bb_pct:.2f})")
            elif bb_pct < 0.2:
                score += 0.75
                reasons.append(f"Price near lower Bollinger Band ({bb_pct:.2f})")
            elif bb_pct > 0.95:
                score -= 1.5
                reasons.append(f"Price at upper Bollinger Band ({bb_pct:.2f})")
            elif bb_pct > 0.8:
                score -= 0.75
                reasons.append(f"Price near upper Bollinger Band ({bb_pct:.2f})")

        # --- Volume Confirmation (weight: 1) ---
        vol_ratio = latest.get("volume_ratio")
        if pd.notna(vol_ratio):
            max_score += 1
            if vol_ratio > 1.5 and score > 0:
                score += 1
                reasons.append(f"High volume confirming move ({vol_ratio:.1f}x avg)")
            elif vol_ratio > 1.5 and score < 0:
                score -= 1
                reasons.append(f"High volume confirming selloff ({vol_ratio:.1f}x avg)")

        # --- ADX Trend Strength (weight: 0.5) ---
        adx = latest.get("adx")
        if pd.notna(adx):
            max_score += 0.5
            if adx > 25:
                reasons.append(f"Strong trend (ADX: {adx:.1f})")
                # Amplify existing signal
                if score > 0:
                    score += 0.5
                elif score < 0:
                    score -= 0.5

        # --- Momentum (weight: 1) ---
        ret_5d = latest.get("return_5d")
        ret_20d = latest.get("return_20d")
        if pd.notna(ret_5d) and pd.notna(ret_20d):
            max_score += 1
            if ret_5d > 0 and ret_20d > 0:
                score += 1
                reasons.append(f"Positive momentum (5d: {ret_5d:.1%}, 20d: {ret_20d:.1%})")
            elif ret_5d < 0 and ret_20d < 0:
                score -= 1
                reasons.append(f"Negative momentum (5d: {ret_5d:.1%}, 20d: {ret_20d:.1%})")

        # --- Compute Signal ---
        if max_score == 0:
            return self._empty_signal()

        # Normalize score to [-1, 1]
        normalized = score / max_score
        confidence = min(abs(normalized), 1.0)

        if normalized > 0.2:
            signal = "BUY"
        elif normalized < -0.2:
            signal = "SELL"
        else:
            signal = "HOLD"

        # Calculate price targets
        close_price = float(latest["close"])
        atr = float(latest.get("atr", close_price * 0.02))
        sr = self.find_support_resistance(df)

        if signal == "BUY":
            entry = close_price
            stop_loss = max(sr["support"][0], close_price - 2 * atr) if sr["support"] else close_price - 2 * atr
            target = sr["resistance"][0] if sr["resistance"] else close_price + 3 * atr
        elif signal == "SELL":
            entry = close_price
            stop_loss = close_price + 2 * atr
            target = sr["support"][0] if sr["support"] else close_price - 3 * atr
        else:
            entry = close_price
            stop_loss = close_price - 2 * atr
            target = close_price + 2 * atr

        risk_reward = abs(target - entry) / abs(entry - stop_loss) if abs(entry - stop_loss) > 0 else 0

        return {
            "signal": signal,
            "confidence": round(confidence, 3),
            "score": round(normalized, 3),
            "reasons": reasons,
            "entry_price": round(entry, 2),
            "stop_loss": round(stop_loss, 2),
            "target_price": round(target, 2),
            "risk_reward_ratio": round(risk_reward, 2),
            "support_levels": sr["support"],
            "resistance_levels": sr["resistance"],
            "indicators": {
                "rsi": round(rsi, 2) if pd.notna(rsi) else None,
                "macd": round(float(macd), 4) if pd.notna(macd) else None,
                "macd_hist": round(float(macd_hist), 4) if pd.notna(macd_hist) else None,
                "adx": round(float(adx), 2) if pd.notna(adx) else None,
                "atr": round(float(atr), 2),
                "bb_pct": round(float(bb_pct), 3) if pd.notna(bb_pct) else None,
                "volume_ratio": round(float(vol_ratio), 2) if pd.notna(vol_ratio) else None,
                "sma_short": round(float(latest.get("sma_short", 0)), 2),
                "sma_long": round(float(latest.get("sma_long", 0)), 2),
            },
        }

    @staticmethod
    def _empty_signal() -> Dict[str, Any]:
        return {
            "signal": "HOLD",
            "confidence": 0.0,
            "score": 0.0,
            "reasons": ["Insufficient data"],
            "entry_price": 0,
            "stop_loss": 0,
            "target_price": 0,
            "risk_reward_ratio": 0,
            "support_levels": [],
            "resistance_levels": [],
            "indicators": {},
        }
