"""
PositionAnalyzer — calls local Nemotron server for per-position risk analysis.

This is distinct from src/llm/analyzer.py (which handles batch screener analysis).
This module focuses on open Schwab/paper portfolio positions, enriching each with
structured risk/signal data for inclusion in the HTML email report.

Usage:
    from src.llm.position_analyzer import PositionAnalyzer
    analyzer = PositionAnalyzer(settings)
    analyses = analyzer.analyze_positions(positions_df, analysis_df)
    # analyses: {"AAPL": {...}, "NVDA": {...}, ...}
"""

import json
import requests
import pandas as pd
from loguru import logger

from src.llm.prompts import SYSTEM_PROMPT, build_user_prompt, fallback_analysis


class PositionAnalyzer:
    """Per-position LLM risk analysis using the local Nemotron server."""

    def __init__(self, settings: dict):
        llm_cfg = settings.get("llm_analysis", {})
        self.base_url = llm_cfg.get("base_url", "http://localhost:8000/v1")
        self.model = llm_cfg.get(
            "model", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-NVFP4"
        )
        self.temperature = llm_cfg.get("temperature", 0.6)
        self.timeout = llm_cfg.get("timeout_seconds", 30)
        self.max_retries = llm_cfg.get("max_retries", 2)
        self.enabled = llm_cfg.get("enabled", False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_positions(
        self,
        positions_df: pd.DataFrame,
        analysis_df: pd.DataFrame | None = None,
    ) -> dict[str, dict]:
        """
        Analyze all positions and return a dict of {ticker: analysis}.

        positions_df: DataFrame with columns from paper_portfolio / Schwab
            (ticker, quantity, avg_cost, current_price, unrealized_pnl,
             unrealized_pnl_pct, market_value)

        analysis_df: Optional DataFrame with strategy recommendations
            (ticker, signal, confidence, composite_score,
             entry_price, stop_loss, target_price, risk_reward_ratio)

        Returns {ticker: llm_analysis_dict} — fallback on per-ticker errors.
        """
        if not self.enabled:
            logger.info("LLM position analysis disabled in config, skipping.")
            return {}

        if positions_df is None or positions_df.empty:
            logger.info("No positions to analyze.")
            return {}

        # Merge positions with strategy analysis where available
        merged = self._merge_data(positions_df, analysis_df)

        results = {}
        for _, row in merged.iterrows():
            ticker = row.get("ticker", "UNKNOWN")
            try:
                results[ticker] = self._analyze_single(row.to_dict())
                logger.debug(f"LLM position analysis complete: {ticker}")
            except Exception as e:
                logger.warning(f"LLM analysis failed for {ticker}: {e}")
                results[ticker] = fallback_analysis(ticker)

        logger.info(
            f"LLM position analysis complete: {len(results)} positions "
            f"({sum(1 for v in results.values() if v['risk_level'] != 'unknown')} successful)"
        )
        return results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _merge_data(
        self,
        positions_df: pd.DataFrame,
        analysis_df: pd.DataFrame | None,
    ) -> pd.DataFrame:
        """Merge positions with analysis data. Analysis fields default to 0/UNKNOWN."""
        df = positions_df.copy()

        if analysis_df is not None and not analysis_df.empty:
            analysis_cols = [
                "ticker", "signal", "confidence", "composite_score",
                "entry_price", "stop_loss", "target_price", "risk_reward_ratio",
            ]
            available = [c for c in analysis_cols if c in analysis_df.columns]
            df = df.merge(
                analysis_df[available],
                on="ticker",
                how="left",
            )

        # Fill missing analysis fields with safe defaults
        defaults = {
            "signal": "UNKNOWN",
            "confidence": 0.0,
            "composite_score": 0.0,
            "entry_price": 0.0,
            "stop_loss": 0.0,
            "target_price": 0.0,
            "risk_reward_ratio": 0.0,
        }
        for col, default in defaults.items():
            if col not in df.columns:
                df[col] = default
            else:
                df[col] = df[col].fillna(default)

        return df

    def _analyze_single(self, ticker_data: dict) -> dict:
        """Run one LLM analysis with retries. Raises on all retries exhausted."""
        ticker = ticker_data.get("ticker", "UNKNOWN")
        prompt = build_user_prompt(ticker_data)
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                content = self._call_api(prompt)
                return self._parse_response(content, ticker)
            except Exception as e:
                last_error = e
                logger.warning(
                    f"LLM attempt {attempt}/{self.max_retries} failed for {ticker}: {e}"
                )

        raise RuntimeError(
            f"All {self.max_retries} attempts failed for {ticker}"
        ) from last_error

    def _call_api(self, prompt: str) -> str:
        """POST to /v1/chat/completions. Returns response content string."""
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "chat_template_kwargs": {"thinking": False},
        }

        response = requests.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()
        return data["choices"][0]["message"]["content"]

    def _parse_response(self, content: str, ticker: str) -> dict:
        """
        Extract JSON from LLM response content.

        Handles:
        - Pure JSON responses
        - JSON wrapped in markdown fences (```json ... ```)
        - Whitespace padding
        """
        content = content.strip()

        # Strip markdown fences if present
        if content.startswith("```"):
            lines = content.splitlines()
            content = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            ).strip()

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(
                f"JSON parse failed for {ticker}: {e}. "
                f"Raw content: {content[:200]}"
            )
            return fallback_analysis(ticker)

        # Ensure ticker field is present and correct
        parsed["ticker"] = ticker

        # Validate risk_level has a known value
        valid_risk = {"low", "medium", "high", "critical", "unknown"}
        if parsed.get("risk_level") not in valid_risk:
            parsed["risk_level"] = "unknown"

        return parsed
