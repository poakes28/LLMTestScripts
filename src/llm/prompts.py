"""
Prompt templates for Nemotron position analysis.

The system prompt locks Nemotron to JSON-only output.
The user prompt builder merges position data + strategy analysis
into a structured prompt for consistent structured responses.
"""

SYSTEM_PROMPT = (
    "You are a quantitative trading risk analyst. "
    "When given position data, you respond ONLY with valid JSON matching the "
    "specified schema. No preamble, no explanation, no markdown fences. "
    "Pure JSON only. Respond with nothing except the JSON object."
)


def build_user_prompt(ticker_data: dict) -> str:
    """
    Build the user prompt for a single position.

    ticker_data keys (all optional with safe defaults):
        ticker, quantity, avg_cost, current_price,
        unrealized_pnl, unrealized_pnl_pct, market_value,
        signal, confidence, composite_score,
        entry_price, stop_loss, target_price, risk_reward_ratio
    """
    t = ticker_data
    return (
        f"Analyze this trading position and return JSON:\n\n"
        f"Ticker: {t.get('ticker', 'UNKNOWN')}\n"
        f"Position: {t.get('quantity', 0)} shares @ avg cost ${t.get('avg_cost', 0):.2f}\n"
        f"Current price: ${t.get('current_price', 0):.2f}\n"
        f"Unrealized P&L: ${t.get('unrealized_pnl', 0):.2f} "
        f"({t.get('unrealized_pnl_pct', 0) * 100:.1f}%)\n"
        f"Market value: ${t.get('market_value', 0):.2f}\n"
        f"Strategy signal: {t.get('signal', 'UNKNOWN')} "
        f"(confidence: {t.get('confidence', 0) * 100:.0f}%)\n"
        f"Composite score: {t.get('composite_score', 0):.3f}\n"
        f"Entry: ${t.get('entry_price', 0):.2f} | "
        f"Stop: ${t.get('stop_loss', 0):.2f} | "
        f"Target: ${t.get('target_price', 0):.2f}\n"
        f"Risk/Reward: {t.get('risk_reward_ratio', 0):.1f}x\n\n"
        'Return JSON:\n'
        '{\n'
        '  "ticker": "<string>",\n'
        '  "risk_level": "<low|medium|high|critical>",\n'
        '  "risk_factors": ["<factor1>", "<factor2>"],\n'
        '  "signal": "<STRONG_BUY|BUY|HOLD|SELL|STRONG_SELL>",\n'
        '  "signal_confidence": <0.0-1.0>,\n'
        '  "key_levels": {"support": <float_or_null>, "resistance": <float_or_null>},\n'
        '  "recommendation": "<1-2 sentence action recommendation>",\n'
        '  "sentiment": "<string>"\n'
        '}'
    )


def fallback_analysis(ticker: str) -> dict:
    """Return a safe fallback when LLM call fails."""
    return {
        "ticker": ticker,
        "risk_level": "unknown",
        "risk_factors": ["LLM analysis unavailable"],
        "signal": "HOLD",
        "signal_confidence": 0.0,
        "key_levels": {"support": None, "resistance": None},
        "recommendation": "Analysis unavailable. Review manually.",
        "sentiment": "neutral",
    }
