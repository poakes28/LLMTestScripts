"""
LLM Analyzer — dual-provider stock analysis.

Provider is selected via ``llm.provider`` in ``config/settings.yaml``:
  "claude"  — Anthropic SDK (requires ``anthropic.api_key`` in credentials.yaml)
  "local"   — OpenAI-compatible API (Ollama, LM Studio, llama.cpp, etc.)

No code changes required to switch between providers; only the config value.
"""

import json
import re
from typing import Any, Dict, List, Optional

from loguru import logger

from src.utils import load_config, load_credentials


SYSTEM_PROMPT = """\
You are a quantitative equity analyst. You will be given a list of stocks with \
their fundamental scores, technical signals, and key metrics. Your task is to:
1. Analyze each stock and provide a rating and brief commentary.
2. Suggest adjustments to the screening criteria based on what you observe.

You MUST return ONLY valid JSON matching this exact structure (no markdown, no explanation):
{
  "stock_commentaries": [
    {
      "ticker": "AAPL",
      "rating": "Buy",
      "summary": "One or two sentence summary.",
      "key_positives": ["point 1", "point 2"],
      "key_risks": ["risk 1"],
      "confidence": "High"
    }
  ],
  "criteria_suggestions": [
    {
      "criterion": "roe_min",
      "current_value": 0.10,
      "suggested_value": 0.15,
      "rationale": "Most high-quality passers have ROE > 15%."
    }
  ],
  "overall_summary": "Brief paragraph summarising the screened batch."
}

Valid rating values: "Strong Buy", "Buy", "Hold", "Avoid"
Valid confidence values: "High", "Medium", "Low"
"""


class LLMAnalyzer:
    """Wraps LLM backends (Claude API or local OpenAI-compat) for stock analysis."""

    def __init__(self):
        cfg = load_config().get("llm", {})
        self.provider = cfg.get("provider", "claude")
        self.max_batch = cfg.get("max_stocks_per_request", 50)
        self.temperature = cfg.get("temperature", 0.3)
        self.max_tokens = cfg.get("max_tokens", 8192)

        if self.provider == "claude":
            try:
                import anthropic
            except ImportError:
                raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

            key = load_credentials().get("anthropic", {}).get("api_key", "")
            if not key:
                raise ValueError(
                    "anthropic.api_key not set in config/credentials.yaml. "
                    "Set it or switch llm.provider to 'local'."
                )
            self.model = cfg.get("model", "claude-sonnet-4-6")
            self._client = anthropic.Anthropic(api_key=key)

        elif self.provider == "local":
            try:
                from openai import OpenAI
            except ImportError:
                raise RuntimeError("openai package not installed. Run: pip install openai")

            base_url = cfg.get("local_base_url", "http://localhost:11434/v1")
            self.model = cfg.get("local_model", "llama3.2")
            self._client = OpenAI(base_url=base_url, api_key="ollama")
        else:
            raise ValueError(f"Unknown llm.provider: {self.provider!r}. Use 'claude' or 'local'.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def analyze_stocks(
        self,
        stocks: List[Dict],
        criteria: Optional[Dict] = None,
        user_notes: str = "",
    ) -> Dict[str, Any]:
        """
        Analyze a list of screened stocks with the configured LLM.

        Args:
            stocks:     List of stock dicts (from screener output).
            criteria:   The screening criteria dict used to produce the list.
            user_notes: Optional free-text instruction appended to the prompt.

        Returns:
            dict with stock_commentaries, criteria_suggestions,
            overall_summary, model_used, provider_used, tokens_used.
        """
        if not stocks:
            return self._empty_response()

        all_commentaries: List[Dict] = []
        all_suggestions: List[Dict] = []
        summaries: List[str] = []
        total_tokens: Optional[int] = 0

        batches = [
            stocks[i : i + self.max_batch]
            for i in range(0, len(stocks), self.max_batch)
        ]

        for batch_idx, batch in enumerate(batches):
            prompt = self._build_prompt(batch, criteria, user_notes, batch_idx, len(batches))
            logger.info(
                f"LLM analysis: batch {batch_idx + 1}/{len(batches)} "
                f"({len(batch)} stocks) via {self.provider}/{self.model}"
            )

            try:
                raw_text, tokens = self._call_llm(prompt)
                parsed = self._parse_json_response(raw_text)
            except Exception as e:
                logger.error(f"LLM call failed (batch {batch_idx + 1}): {e}")
                parsed = self._empty_batch_response(batch)
                tokens = None

            all_commentaries.extend(parsed.get("stock_commentaries", []))
            all_suggestions.extend(parsed.get("criteria_suggestions", []))
            if parsed.get("overall_summary"):
                summaries.append(parsed["overall_summary"])

            if total_tokens is not None and tokens is not None:
                total_tokens += tokens
            else:
                total_tokens = None

        # Deduplicate criteria suggestions by criterion name
        seen_criteria: set = set()
        deduped_suggestions = []
        for s in all_suggestions:
            c = s.get("criterion", "")
            if c not in seen_criteria:
                deduped_suggestions.append(s)
                seen_criteria.add(c)

        return {
            "stock_commentaries": all_commentaries,
            "criteria_suggestions": deduped_suggestions,
            "overall_summary": " ".join(summaries) if summaries else "",
            "model_used": self.model,
            "provider_used": self.provider,
            "tokens_used": total_tokens,
        }

    def check_status(self) -> Dict[str, Any]:
        """Verify the configured provider responds. Returns status dict."""
        try:
            test_text, _ = self._call_llm('Reply with exactly: {"ok": true}')
            return {
                "provider": self.provider,
                "model": self.model,
                "status": "ok",
                "response_preview": test_text[:120],
            }
        except Exception as e:
            return {
                "provider": self.provider,
                "model": self.model,
                "status": "error",
                "error": str(e),
            }

    # ------------------------------------------------------------------
    # LLM dispatch
    # ------------------------------------------------------------------
    def _call_llm(self, prompt: str):
        """Call the configured backend. Returns (response_text, tokens_used)."""
        if self.provider == "claude":
            msg = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            text = msg.content[0].text
            tokens = msg.usage.input_tokens + msg.usage.output_tokens
            return text, tokens

        else:  # local / openai-compat
            resp = self._client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            text = resp.choices[0].message.content
            tokens = None  # local providers may not report usage
            return text, tokens

    # ------------------------------------------------------------------
    # Prompt builder
    # ------------------------------------------------------------------
    def _build_prompt(
        self,
        stocks: List[Dict],
        criteria: Optional[Dict],
        user_notes: str,
        batch_idx: int,
        total_batches: int,
    ) -> str:
        lines = []

        if total_batches > 1:
            lines.append(f"[Batch {batch_idx + 1} of {total_batches}]")
            lines.append("")

        if criteria:
            lines.append("=== Screening Criteria Used ===")
            for k, v in criteria.items():
                if v is not None and v != [] and v is not False:
                    lines.append(f"  {k}: {v}")
            lines.append("")

        lines.append(f"=== Screened Stocks ({len(stocks)}) ===")
        for s in stocks:
            lines.append(f"\nTicker: {s.get('ticker', '?')}")
            lines.append(f"  Name: {s.get('name', '')}")
            lines.append(f"  Sector: {s.get('sector', '')}")
            lines.append(f"  Fundamental Score: {s.get('fundamental_score', 0):.1f}/100")
            lines.append(f"  Fundamental Signal: {s.get('fundamental_signal', 'N/A')}")
            lines.append(f"  Technical Signal: {s.get('technical_signal', 'N/A')}")
            lines.append(f"  Technical Confidence: {s.get('technical_confidence', 0):.2f}")
            lines.append(f"  Composite Score: {s.get('composite_score', 0):.4f}")

            metrics = s.get("metrics", {})
            if metrics:
                lines.append("  Key Metrics:")
                for mk, mv in metrics.items():
                    if mv is not None:
                        lines.append(f"    {mk}: {mv}")

            reasons = s.get("reasons", [])
            if reasons:
                lines.append(f"  Analyst Notes: {'; '.join(reasons[:5])}")

        if user_notes:
            lines.append(f"\n=== User Notes ===\n{user_notes}")

        lines.append("\nAnalyze each stock and return the JSON as specified in the system prompt.")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # JSON parsing with fallback
    # ------------------------------------------------------------------
    def _parse_json_response(self, text: str) -> Dict:
        """Extract and parse JSON from LLM response, with regex fallback."""
        # Try direct parse first
        stripped = text.strip()
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

        # Look for JSON block in markdown code fences
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Find the outermost {...} block
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(stripped[start : end + 1])
            except json.JSONDecodeError:
                pass

        logger.warning("Could not parse LLM JSON response; returning empty structure")
        return {"stock_commentaries": [], "criteria_suggestions": [], "overall_summary": text[:500]}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _empty_response(self) -> Dict:
        return {
            "stock_commentaries": [],
            "criteria_suggestions": [],
            "overall_summary": "No stocks provided for analysis.",
            "model_used": self.model,
            "provider_used": self.provider,
            "tokens_used": 0,
        }

    def _empty_batch_response(self, stocks: List[Dict]) -> Dict:
        """Fallback response when LLM call fails."""
        return {
            "stock_commentaries": [
                {
                    "ticker": s.get("ticker", "?"),
                    "rating": "Hold",
                    "summary": "Analysis unavailable due to LLM error.",
                    "key_positives": [],
                    "key_risks": [],
                    "confidence": "Low",
                }
                for s in stocks
            ],
            "criteria_suggestions": [],
            "overall_summary": "LLM analysis failed for this batch.",
        }
