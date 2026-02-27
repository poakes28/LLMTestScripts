"""
Fundamental Analysis Engine.

Evaluates stocks based on value metrics, growth, profitability,
financial health, and quality. Generates fundamental buy/sell signals.
"""

from typing import Optional, Dict, Any, Tuple, List

import numpy as np
import pandas as pd
from loguru import logger

from src.utils import load_config


class FundamentalAnalyzer:
    """Scores stocks on fundamental metrics and generates value signals."""

    def __init__(self, criteria: Optional[Dict] = None):
        config = load_config()
        self.defaults = config.get("fundamental_defaults", {})
        self.criteria = {**self.defaults, **(criteria or {})}

    def score_stock(self, f: Dict[str, Any]) -> Dict[str, Any]:
        """
        Score a single stock on fundamental metrics.
        f: dict of fundamental data (from yfinance .info)
        Returns signal, confidence, breakdown, and reasons.
        """
        scores = {}
        reasons = []
        max_possible = 0

        # Valuation (30 pts)
        s, r = self._score_valuation(f)
        scores["valuation"] = s; reasons.extend(r); max_possible += 30

        # Profitability (25 pts)
        s, r = self._score_profitability(f)
        scores["profitability"] = s; reasons.extend(r); max_possible += 25

        # Growth (20 pts)
        s, r = self._score_growth(f)
        scores["growth"] = s; reasons.extend(r); max_possible += 20

        # Financial Health (15 pts)
        s, r = self._score_health(f)
        scores["financial_health"] = s; reasons.extend(r); max_possible += 15

        # Quality (10 pts)
        s, r = self._score_quality(f)
        scores["quality"] = s; reasons.extend(r); max_possible += 10

        total = sum(scores.values())
        normalized = total / max_possible if max_possible > 0 else 0

        if normalized >= 0.6:
            signal = "BUY"
        elif normalized <= 0.3:
            signal = "SELL"
        else:
            signal = "HOLD"

        confidence = min(abs(normalized - 0.5) * 2, 1.0)

        return {
            "signal": signal,
            "confidence": round(confidence, 3),
            "total_score": round(total, 1),
            "max_score": max_possible,
            "normalized_score": round(normalized, 3),
            "scores": scores,
            "reasons": reasons,
            "metrics": self._extract_key_metrics(f),
        }

    # ------------------------------------------------------------------
    # Category Scoring
    # ------------------------------------------------------------------
    def _safe(self, val) -> Optional[float]:
        """Return float or None for NaN/None values."""
        if val is None:
            return None
        try:
            v = float(val)
            return None if np.isnan(v) else v
        except (ValueError, TypeError):
            return None

    def _score_valuation(self, f: Dict) -> Tuple[float, List[str]]:
        score = 0.0
        reasons = []

        pe = self._safe(f.get("pe_ratio"))
        pe_max = self.criteria.get("pe_ratio_max", 25)
        if pe is not None and pe > 0:
            if pe < 10:
                score += 10; reasons.append(f"Deep value P/E: {pe:.1f}")
            elif pe < 15:
                score += 8; reasons.append(f"Value P/E: {pe:.1f}")
            elif pe < pe_max:
                score += 5; reasons.append(f"Reasonable P/E: {pe:.1f}")
            elif pe < 40:
                score += 2
            else:
                reasons.append(f"Expensive P/E: {pe:.1f}")

        peg = self._safe(f.get("peg_ratio"))
        if peg is not None and peg > 0:
            if peg < 1.0:
                score += 8; reasons.append(f"Undervalued PEG: {peg:.2f}")
            elif peg < 1.5:
                score += 5
            elif peg < 2.0:
                score += 2

        pb = self._safe(f.get("price_to_book"))
        if pb is not None and pb > 0:
            if pb < 1.0:
                score += 6; reasons.append(f"Below book value: P/B {pb:.2f}")
            elif pb < 3.0:
                score += 4
            elif pb < 5.0:
                score += 2

        ev = self._safe(f.get("ev_to_ebitda"))
        if ev is not None and ev > 0:
            if ev < 8:
                score += 6; reasons.append(f"Low EV/EBITDA: {ev:.1f}")
            elif ev < 12:
                score += 4
            elif ev < 20:
                score += 2

        return score, reasons

    def _score_profitability(self, f: Dict) -> Tuple[float, List[str]]:
        score = 0.0
        reasons = []

        roe = self._safe(f.get("roe"))
        if roe is not None:
            if roe > 0.25:
                score += 10; reasons.append(f"Excellent ROE: {roe:.1%}")
            elif roe > 0.18:
                score += 8; reasons.append(f"Strong ROE: {roe:.1%}")
            elif roe > self.criteria.get("roe_min", 0.12):
                score += 6
            elif roe > 0.05:
                score += 3
            else:
                reasons.append(f"Weak ROE: {roe:.1%}")

        margin = self._safe(f.get("profit_margin"))
        if margin is not None:
            if margin > 0.25:
                score += 8; reasons.append(f"High margin: {margin:.1%}")
            elif margin > 0.15:
                score += 6
            elif margin > 0.10:
                score += 4
            elif margin > 0:
                score += 2

        op = self._safe(f.get("operating_margin"))
        if op is not None:
            if op > 0.30:
                score += 7
            elif op > 0.20:
                score += 5
            elif op > 0.10:
                score += 3

        return score, reasons

    def _score_growth(self, f: Dict) -> Tuple[float, List[str]]:
        score = 0.0
        reasons = []

        rev = self._safe(f.get("revenue_growth"))
        if rev is not None:
            if rev > 0.25:
                score += 10; reasons.append(f"Strong revenue growth: {rev:.1%}")
            elif rev > 0.15:
                score += 8
            elif rev > self.criteria.get("revenue_growth_min", 0.05):
                score += 5
            elif rev > 0:
                score += 2
            else:
                reasons.append(f"Declining revenue: {rev:.1%}")

        earn = self._safe(f.get("earnings_growth"))
        if earn is not None:
            if earn > 0.25:
                score += 10; reasons.append(f"Strong earnings growth: {earn:.1%}")
            elif earn > 0.15:
                score += 7
            elif earn > 0.05:
                score += 4
            elif earn > 0:
                score += 2
            else:
                reasons.append(f"Declining earnings: {earn:.1%}")

        return score, reasons

    def _score_health(self, f: Dict) -> Tuple[float, List[str]]:
        score = 0.0
        reasons = []

        de = self._safe(f.get("debt_to_equity"))
        de_max = self.criteria.get("debt_to_equity_max", 1.5)
        if de is not None:
            if de < 0.3:
                score += 8; reasons.append(f"Very low debt: D/E {de:.2f}")
            elif de < 0.8:
                score += 6
            elif de < de_max:
                score += 3
            else:
                reasons.append(f"High debt: D/E {de:.2f}")

        cr = self._safe(f.get("current_ratio"))
        if cr is not None:
            if cr > 2.0:
                score += 7; reasons.append(f"Strong liquidity: CR {cr:.2f}")
            elif cr > self.criteria.get("current_ratio_min", 1.2):
                score += 5
            elif cr > 1.0:
                score += 2
            else:
                reasons.append(f"Liquidity concern: CR {cr:.2f}")

        return score, reasons

    def _score_quality(self, f: Dict) -> Tuple[float, List[str]]:
        score = 0.0
        reasons = []

        roa = self._safe(f.get("roa"))
        if roa is not None and roa > 0.10:
            score += 4; reasons.append(f"High ROA: {roa:.1%}")
        elif roa is not None and roa > 0.05:
            score += 2

        div = self._safe(f.get("dividend_yield"))
        if div is not None and div > 0.02:
            score += 3; reasons.append(f"Pays dividend: {div:.1%}")
        elif div is not None and div > 0:
            score += 1

        fcf = self._safe(f.get("free_cash_flow"))
        if fcf is not None and fcf > 0:
            score += 3
            reasons.append("Positive free cash flow")

        return score, reasons

    def _extract_key_metrics(self, f: Dict) -> Dict:
        """Extract clean dict of key metrics for reporting."""
        keys = [
            "pe_ratio", "forward_pe", "peg_ratio", "price_to_book",
            "ev_to_ebitda", "roe", "roa", "profit_margin", "operating_margin",
            "revenue_growth", "earnings_growth", "debt_to_equity",
            "current_ratio", "dividend_yield", "beta", "market_cap",
        ]
        result = {}
        for k in keys:
            v = self._safe(f.get(k))
            result[k] = round(v, 4) if v is not None else None
        return result
