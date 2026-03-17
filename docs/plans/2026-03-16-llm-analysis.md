# Trading System + LLM Analysis Layer — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Duplicate the existing trading system to `~/Desktop/LLMTestScripts/`, add a local Nemotron LLM analysis layer that annotates each position with structured JSON risk/signal data in the HTML email report, configure Cline to use the local Nemotron server for coding, and push the result to a new GitHub repo.

**Architecture:** Per-position LLM calls (one HTTP POST per ticker to `localhost:8000/v1/chat/completions`) after positions load, before report generation. New `src/llm/` module handles prompts and API calls. `ReportGenerator` gains an optional `llm_analyses` parameter and a new `_build_llm_section()` rendering method. All failures degrade gracefully — report always sends.

**Tech Stack:** Python 3.12, pandas, requests (already in requirements.txt), loguru, pyyaml, matplotlib, Nemotron NVFP4 via OpenAI-compatible API at localhost:8000, GitHub CLI (`gh`), git

---

## Task 1: Copy Project & Initialize Git

**Files:**
- Create: `~/Desktop/LLMTestScripts/` (full copy of trading-system)

**Step 1: Copy the project**

```bash
cp -r /home/peter-oakes/Downloads/trading-system ~/Desktop/LLMTestScripts
```

**Step 2: Verify copy**

```bash
ls ~/Desktop/LLMTestScripts/src/
```
Expected output: `analysis  backtest  collector  reporting  utils.py`

**Step 3: Initialize git repo**

```bash
cd ~/Desktop/LLMTestScripts
git init
git add .
git commit -m "feat: initial copy of trading-system base"
```

**Step 4: Create GitHub repo and push**

```bash
gh repo create LLMTestScripts \
  --public \
  --description "Trading analysis system with local Nemotron LLM risk analysis layer" \
  --source=. \
  --remote=origin \
  --push
```

Expected: Repo created at `https://github.com/poakes28/LLMTestScripts`

---

## Task 2: Create `src/llm/` Package

**Files:**
- Create: `~/Desktop/LLMTestScripts/src/llm/__init__.py`
- Create: `~/Desktop/LLMTestScripts/src/llm/prompts.py`
- Create: `~/Desktop/LLMTestScripts/src/llm/analyzer.py`

**Step 1: Create package marker**

File: `src/llm/__init__.py`
```python
"""LLM analysis module — per-position Nemotron risk analysis."""
```

**Step 2: Create `src/llm/prompts.py`**

```python
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
```

**Step 3: Create `src/llm/analyzer.py`**

```python
"""
LLM Analyzer — calls local Nemotron server for per-position risk analysis.

Usage:
    from src.llm.analyzer import LLMAnalyzer
    analyzer = LLMAnalyzer(settings)
    analyses = analyzer.analyze_positions(positions_df, analysis_df)
    # analyses: {"AAPL": {...}, "NVDA": {...}, ...}
"""

import json
import requests
import pandas as pd
from loguru import logger

from src.llm.prompts import SYSTEM_PROMPT, build_user_prompt, fallback_analysis


class LLMAnalyzer:
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
            logger.info("LLM analysis disabled in config, skipping.")
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
                logger.debug(f"LLM analysis complete: {ticker}")
            except Exception as e:
                logger.warning(f"LLM analysis failed for {ticker}: {e}")
                results[ticker] = fallback_analysis(ticker)

        logger.info(
            f"LLM analysis complete: {len(results)} positions "
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
            # Remove first and last fence lines
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
```

**Step 4: Commit**

```bash
cd ~/Desktop/LLMTestScripts
git add src/llm/
git commit -m "feat: add src/llm package with LLMAnalyzer and prompt templates"
```

---

## Task 3: Update `config/settings.yaml`

**Files:**
- Modify: `~/Desktop/LLMTestScripts/config/settings.yaml`

**Step 1: Append `llm_analysis` section at end of file**

Add to the bottom of `config/settings.yaml`:

```yaml

# ----------------------------------------------------------------------------
# LLM Analysis Configuration (Nemotron local server)
# ----------------------------------------------------------------------------
llm_analysis:
  enabled: true
  base_url: "http://localhost:8000/v1"
  model: "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-NVFP4"
  temperature: 0.6
  timeout_seconds: 30
  max_retries: 2
```

**Step 2: Commit**

```bash
cd ~/Desktop/LLMTestScripts
git add config/settings.yaml
git commit -m "feat: add llm_analysis config section"
```

---

## Task 4: Modify `scripts/report.py`

**Files:**
- Modify: `~/Desktop/LLMTestScripts/scripts/report.py`

**Step 1: Replace the `main()` function**

The current `main()` at line 28 through end of file becomes:

```python
def main():
    parser = argparse.ArgumentParser(description="Trading System Email Reporter")
    parser.add_argument("--preview", action="store_true",
                        help="Save report locally without sending email")
    parser.add_argument("--open", action="store_true",
                        help="Open report in browser after generating")
    parser.add_argument("--output", type=str, default=None,
                        help="Custom output path for HTML file")
    args = parser.parse_args()

    setup_logging("reporter")
    logger.info("=" * 60)
    logger.info("EMAIL REPORTER STARTING")
    logger.info("=" * 60)

    try:
        from src.utils import load_config
        from src.llm.analyzer import LLMAnalyzer

        settings = load_config()

        # Run LLM position analysis before building report
        llm_analyses = {}
        if settings.get("llm_analysis", {}).get("enabled", False):
            try:
                from src.collector.paper_portfolio import PaperPortfolioManager
                import pandas as pd

                portfolio_mgr = PaperPortfolioManager()
                all_positions = []
                for fund_name in settings.get("funds", {}):
                    portfolio = portfolio_mgr.get_portfolio(fund_name)
                    positions = portfolio.get_positions()
                    if not positions.empty:
                        all_positions.append(positions)

                if all_positions:
                    positions_df = pd.concat(all_positions, ignore_index=True)
                    positions_df = positions_df.drop_duplicates(subset=["ticker"])
                else:
                    positions_df = pd.DataFrame()

                # Load latest strategy analysis for the first fund (all share same tickers)
                from src.utils import load_parquet
                analysis_df = None
                for fund_name in settings.get("funds", {}):
                    analysis_df = load_parquet("analysis", f"recommendations_{fund_name}")
                    if analysis_df is not None and not analysis_df.empty:
                        break

                analyzer = LLMAnalyzer(settings)
                llm_analyses = analyzer.analyze_positions(positions_df, analysis_df)
                logger.info(f"LLM analysis complete: {len(llm_analyses)} positions analyzed")

            except Exception as e:
                logger.warning(f"LLM analysis failed, continuing without it: {e}")

        # Generate report
        generator = ReportGenerator()
        html = generator.generate_report(llm_analyses=llm_analyses)

        # Save locally
        if args.output:
            output_path = args.output
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                f.write(html)
        else:
            output_path = generator.save_report(html)

        logger.info(f"Report saved to: {output_path}")

        # Open in browser if requested
        if args.open:
            webbrowser.open(f"file://{os.path.abspath(output_path)}")

        # Send email (unless preview mode)
        if not args.preview:
            sender = EmailSender()
            if sender.is_configured:
                success = sender.send_report(html)
                if success:
                    logger.info("Report emailed successfully")
                else:
                    logger.warning("Email sending failed")
            else:
                logger.info("Email not configured. Report saved locally only.")
        else:
            logger.info("Preview mode - email not sent")

        logger.info("Reporting complete")

    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        raise
```

**Step 2: Commit**

```bash
cd ~/Desktop/LLMTestScripts
git add scripts/report.py
git commit -m "feat: wire LLMAnalyzer into report.py before report generation"
```

---

## Task 5: Modify `src/reporting/report_generator.py`

**Files:**
- Modify: `~/Desktop/LLMTestScripts/src/reporting/report_generator.py`

**Step 1: Update `generate_report()` signature (line 48)**

Replace:
```python
    def generate_report(self) -> str:
        """
        Generate the full morning email report as HTML.
        Returns HTML string ready for sending.
        """
        logger.info("Generating email report...")

        # Gather data
        portfolio_mgr = PaperPortfolioManager()
        summaries = portfolio_mgr.get_all_summaries()

        fund_sections = []
        for fund_name in self.config.get("funds", {}):
            section = self._generate_fund_section(fund_name, portfolio_mgr)
            fund_sections.append(section)

        # Build report
        report_date = date.today().strftime("%B %d, %Y")
        html = self._render_html(report_date, summaries, fund_sections)

        logger.info("Report generated successfully")
        return html
```

With:
```python
    def generate_report(self, llm_analyses: Optional[Dict[str, Dict]] = None) -> str:
        """
        Generate the full morning email report as HTML.

        Args:
            llm_analyses: Optional dict of {ticker: llm_analysis_dict} from LLMAnalyzer.
                          If None or empty, LLM section is omitted from all fund sections.

        Returns HTML string ready for sending.
        """
        logger.info("Generating email report...")
        llm_analyses = llm_analyses or {}

        # Gather data
        portfolio_mgr = PaperPortfolioManager()
        summaries = portfolio_mgr.get_all_summaries()

        fund_sections = []
        for fund_name in self.config.get("funds", {}):
            section = self._generate_fund_section(
                fund_name, portfolio_mgr, llm_analyses
            )
            fund_sections.append(section)

        # Build report
        report_date = date.today().strftime("%B %d, %Y")
        html = self._render_html(report_date, summaries, fund_sections)

        logger.info("Report generated successfully")
        return html
```

**Step 2: Update `_generate_fund_section()` signature (line 71)**

Replace:
```python
    def _generate_fund_section(self, fund_name: str, portfolio_mgr: PaperPortfolioManager) -> Dict:
        """Generate data for one fund's report section."""
        fund_cfg = self.config["funds"][fund_name]
        portfolio = portfolio_mgr.get_portfolio(fund_name)
        summary = portfolio.get_portfolio_summary()
        positions = portfolio.get_positions()

        # Get recommendations
        top_buys = self.strategy.get_top_buys(fund_name, self.max_recs)
        top_sells = self.strategy.get_top_sells(fund_name, self.max_recs)

        # Generate charts
        equity_chart = self._generate_equity_chart(fund_name)
        allocation_chart = self._generate_allocation_chart(positions, fund_cfg["name"])

        return {
            "fund_name": fund_cfg["name"],
            "fund_key": fund_name,
            "summary": summary,
            "positions": positions.to_dict("records") if not positions.empty else [],
            "top_buys": top_buys,
            "top_sells": top_sells,
            "equity_chart": equity_chart,
            "allocation_chart": allocation_chart,
        }
```

With:
```python
    def _generate_fund_section(
        self,
        fund_name: str,
        portfolio_mgr: PaperPortfolioManager,
        llm_analyses: Dict[str, Dict],
    ) -> Dict:
        """Generate data for one fund's report section."""
        fund_cfg = self.config["funds"][fund_name]
        portfolio = portfolio_mgr.get_portfolio(fund_name)
        summary = portfolio.get_portfolio_summary()
        positions = portfolio.get_positions()

        # Get recommendations
        top_buys = self.strategy.get_top_buys(fund_name, self.max_recs)
        top_sells = self.strategy.get_top_sells(fund_name, self.max_recs)

        # Generate charts
        equity_chart = self._generate_equity_chart(fund_name)
        allocation_chart = self._generate_allocation_chart(positions, fund_cfg["name"])

        # Filter LLM analyses to tickers in this fund's positions
        position_tickers = set(positions["ticker"].tolist()) if not positions.empty else set()
        fund_llm = {t: a for t, a in llm_analyses.items() if t in position_tickers}

        return {
            "fund_name": fund_cfg["name"],
            "fund_key": fund_name,
            "summary": summary,
            "positions": positions.to_dict("records") if not positions.empty else [],
            "top_buys": top_buys,
            "top_sells": top_sells,
            "equity_chart": equity_chart,
            "allocation_chart": allocation_chart,
            "llm_analyses": fund_llm,
        }
```

**Step 3: Update `_render_fund_section()` to include LLM block (line 248)**

Replace:
```python
    def _render_fund_section(self, section: Dict) -> str:
        """Render HTML for a single fund section."""
        s = section["summary"]
        equity_img = section["equity_chart"]
        alloc_img = section["allocation_chart"]

        # Recommendations table
        buys_html = self._render_recommendations_table(section["top_buys"], "BUY")
        sells_html = self._render_recommendations_table(section["top_sells"], "SELL")

        # Positions table
        positions_html = self._render_positions_table(section["positions"])

        return f"""
<div style="margin:30px 0;border:1px solid #333;border-radius:10px;overflow:hidden;">
    <!-- Fund Header -->
    <div style="background:#16213e;padding:16px 20px;">
        <h2 style="color:white;margin:0;font-size:18px;">{section['fund_name']}</h2>
        <span style="color:#888;font-size:12px;">
            {fmt_currency(s['total_value'])} | {s.get('num_positions', 0)} positions
        </span>
    </div>

    <!-- Charts -->
    <div style="display:flex;flex-wrap:wrap;padding:16px;gap:16px;">
        <div style="flex:2;min-width:300px;">
            <img src="data:image/png;base64,{equity_img}" style="width:100%;border-radius:6px;" alt="Equity Curve">
        </div>
        <div style="flex:1;min-width:200px;">
            <img src="data:image/png;base64,{alloc_img}" style="width:100%;border-radius:6px;" alt="Allocation">
        </div>
    </div>

    <!-- Current Positions -->
    <div style="padding:0 20px 16px;">
        <h3 style="color:#00d4ff;font-size:14px;margin:0 0 8px;">Current Positions</h3>
        {positions_html}
    </div>

    <!-- Buy Recommendations -->
    <div style="padding:0 20px 16px;">
        <h3 style="color:#4ade80;font-size:14px;margin:0 0 8px;">Top Buy Recommendations</h3>
        {buys_html}
    </div>

    <!-- Sell Recommendations -->
    <div style="padding:0 20px 20px;">
        <h3 style="color:#ff6b6b;font-size:14px;margin:0 0 8px;">Top Sell Recommendations</h3>
        {sells_html}
    </div>
</div>"""
```

With:
```python
    def _render_fund_section(self, section: Dict) -> str:
        """Render HTML for a single fund section."""
        s = section["summary"]
        equity_img = section["equity_chart"]
        alloc_img = section["allocation_chart"]

        # Recommendations table
        buys_html = self._render_recommendations_table(section["top_buys"], "BUY")
        sells_html = self._render_recommendations_table(section["top_sells"], "SELL")

        # Positions table
        positions_html = self._render_positions_table(section["positions"])

        # LLM analysis block (empty string if no analyses for this fund)
        llm_html = self._build_llm_section(
            section["positions"], section.get("llm_analyses", {})
        )

        return f"""
<div style="margin:30px 0;border:1px solid #333;border-radius:10px;overflow:hidden;">
    <!-- Fund Header -->
    <div style="background:#16213e;padding:16px 20px;">
        <h2 style="color:white;margin:0;font-size:18px;">{section['fund_name']}</h2>
        <span style="color:#888;font-size:12px;">
            {fmt_currency(s['total_value'])} | {s.get('num_positions', 0)} positions
        </span>
    </div>

    <!-- Charts -->
    <div style="display:flex;flex-wrap:wrap;padding:16px;gap:16px;">
        <div style="flex:2;min-width:300px;">
            <img src="data:image/png;base64,{equity_img}" style="width:100%;border-radius:6px;" alt="Equity Curve">
        </div>
        <div style="flex:1;min-width:200px;">
            <img src="data:image/png;base64,{alloc_img}" style="width:100%;border-radius:6px;" alt="Allocation">
        </div>
    </div>

    <!-- Current Positions -->
    <div style="padding:0 20px 16px;">
        <h3 style="color:#00d4ff;font-size:14px;margin:0 0 8px;">Current Positions</h3>
        {positions_html}
    </div>

    {llm_html}

    <!-- Buy Recommendations -->
    <div style="padding:0 20px 16px;">
        <h3 style="color:#4ade80;font-size:14px;margin:0 0 8px;">Top Buy Recommendations</h3>
        {buys_html}
    </div>

    <!-- Sell Recommendations -->
    <div style="padding:0 20px 20px;">
        <h3 style="color:#ff6b6b;font-size:14px;margin:0 0 8px;">Top Sell Recommendations</h3>
        {sells_html}
    </div>
</div>"""
```

**Step 4: Add `_build_llm_section()` method**

Add this new method after `_render_positions_table()` (after line 369, before `save_report`):

```python
    def _build_llm_section(
        self, positions: List[Dict], llm_analyses: Dict[str, Dict]
    ) -> str:
        """
        Render the AI Risk Analysis section for a fund.

        Returns empty string if no LLM analyses are available,
        so the report renders cleanly without an empty section.
        """
        if not llm_analyses:
            return ""

        # Only render cards for positions that have LLM analysis
        tickers_with_analysis = [
            p["ticker"] for p in positions
            if p.get("ticker") in llm_analyses
        ]
        if not tickers_with_analysis:
            return ""

        risk_colors = {
            "low":      "#00b300",
            "medium":   "#e6b800",
            "high":     "#ff6600",
            "critical": "#cc0000",
            "unknown":  "#666666",
        }

        cards_html = ""
        for ticker in tickers_with_analysis:
            a = llm_analyses[ticker]
            risk_level = a.get("risk_level", "unknown")
            risk_color = risk_colors.get(risk_level, "#666666")
            conf_pct = int(a.get("signal_confidence", 0) * 100)

            risk_factors_html = "".join(
                f'<div style="color:#bbb;font-size:11px;margin:2px 0;">'
                f'&bull; {factor}</div>'
                for factor in a.get("risk_factors", [])
            )

            support = a.get("key_levels", {}).get("support")
            resistance = a.get("key_levels", {}).get("resistance")
            support_str = f"${support:.2f}" if support else "N/A"
            resistance_str = f"${resistance:.2f}" if resistance else "N/A"

            cards_html += f"""
            <div style="display:flex;border:1px solid #2a2a4a;border-radius:8px;
                        margin:6px 0;overflow:hidden;background:#111128;">
                <!-- Col 1: Ticker + levels -->
                <div style="padding:12px 14px;min-width:130px;border-right:1px solid #2a2a4a;">
                    <div style="color:white;font-weight:bold;font-size:14px;">{ticker}</div>
                    <div style="color:#888;font-size:10px;margin-top:6px;">Support</div>
                    <div style="color:#4ade80;font-size:12px;">{support_str}</div>
                    <div style="color:#888;font-size:10px;margin-top:4px;">Resistance</div>
                    <div style="color:#ff6b6b;font-size:12px;">{resistance_str}</div>
                </div>
                <!-- Col 2: Risk level + factors -->
                <div style="padding:12px 14px;flex:1;border-right:1px solid #2a2a4a;">
                    <div style="color:{risk_color};font-weight:bold;font-size:12px;
                                text-transform:uppercase;">
                        RISK: {risk_level.upper()}
                    </div>
                    <div style="margin-top:6px;">{risk_factors_html}</div>
                </div>
                <!-- Col 3: Signal + recommendation -->
                <div style="padding:12px 14px;flex:2;">
                    <div style="display:flex;align-items:center;gap:8px;">
                        <span style="color:#00d4ff;font-weight:bold;font-size:12px;">
                            {a.get("signal", "HOLD")}
                        </span>
                        <div style="background:#333;border-radius:3px;height:10px;width:60px;">
                            <div style="background:#00d4ff;border-radius:3px;height:10px;
                                        width:{conf_pct}%;"></div>
                        </div>
                        <span style="color:#888;font-size:10px;">{conf_pct}%</span>
                    </div>
                    <div style="color:#ccc;font-size:11px;margin-top:6px;line-height:1.4;">
                        {a.get("recommendation", "")}
                    </div>
                    <div style="color:#666;font-size:10px;margin-top:4px;font-style:italic;">
                        {a.get("sentiment", "")}
                    </div>
                </div>
            </div>"""

        return f"""
    <!-- AI Risk Analysis -->
    <div style="padding:0 20px 16px;">
        <h3 style="color:#a78bfa;font-size:14px;margin:0 0 8px;">
            AI Risk Analysis
            <span style="color:#555;font-size:10px;font-weight:normal;margin-left:8px;">
                Nemotron Nano 30B &bull; NVFP4
            </span>
        </h3>
        {cards_html}
    </div>"""
```

**Step 5: Commit**

```bash
cd ~/Desktop/LLMTestScripts
git add src/reporting/report_generator.py
git commit -m "feat: add LLM analysis section to HTML report"
```

---

## Task 6: Create Cline Configuration Files

**Files:**
- Create: `~/Desktop/LLMTestScripts/.clinerules`
- Create: `~/Desktop/LLMTestScripts/.vscode/settings.json`
- Create: `~/Desktop/LLMTestScripts/.mcp.json`

**Step 1: Create `.clinerules`**

```markdown
# Trading System — Cline Project Rules

## This Project
Local LLM-augmented trading analysis system. Three independent entry points:
collect.py → analyze.py → report.py, connected via Parquet files in data/.
The src/llm/ module adds per-position Nemotron analysis to the email report.

## Tech Stack
- Python 3.12, pandas, pandas-ta, yfinance, loguru, pyyaml, requests
- Data storage: Parquet files via pyarrow — NO databases, NO SQLite, NO CSV
- HTML generation: f-strings with inline CSS — NO Jinja2 (it's in requirements but unused)
- Charts: matplotlib embedded as base64 PNG in HTML
- Logging: loguru — NOT stdlib logging, NOT print statements
- Config: config/settings.yaml + config/credentials.yaml — NEVER hardcode credentials

## Project Layout
```
src/
  collector/   — price_fetcher.py, schwab_client.py, paper_portfolio.py
  analysis/    — technical.py, fundamental.py, risk_metrics.py, strategies.py
  llm/         — analyzer.py (LLMAnalyzer class), prompts.py (prompt templates)
  reporting/   — report_generator.py (HTML), email_sender.py (SMTP)
  utils.py     — load_config(), fmt_pct(), fmt_currency(), save/load_parquet()
scripts/
  collect.py   — entry: fetch prices + sync Schwab
  analyze.py   — entry: run strategy analysis
  report.py    — entry: generate + email report (calls LLMAnalyzer)
config/
  settings.yaml       — all non-secret config including llm_analysis section
  credentials.yaml    — Schwab keys, email creds (user fills manually)
data/                 — Parquet files, auto-created at runtime
```

## Data Conventions
- All monetary values: float, 2 decimal places
- P&L percentages: float as decimal (0.15 = 15%, NOT 15.0)
- Ticker symbols: uppercase strings
- Fund keys: "fundamental", "technical", "balanced" (match settings.yaml)
- Parquet column names are sacred — don't rename them

## Error Handling Pattern
Always wrap Schwab API and LLM API calls in try/except, log a warning, and continue.
The report must always send even if LLM or Schwab fails. Never let external
service failures crash the pipeline.

## What NOT to Change
- Parquet schema column names (everything downstream depends on exact names)
- config/credentials.yaml structure (user fills this manually, don't reorder)
- The three entry point script CLI argument interfaces
- Email MIME structure in src/reporting/email_sender.py

## LLM Analysis Module (src/llm/)
- LLM responses must be valid JSON; use fallback_analysis() on parse failure
- Reasoning disabled: always pass `"chat_template_kwargs": {"thinking": False}`
- Temperature: 0.6 (from config, don't hardcode)
- One call per position, sequential — don't batch or parallelize without discussion

## Testing / Verification
```bash
# Preview report (no email sent, opens in browser)
cd ~/Desktop/LLMTestScripts
python scripts/report.py --preview --open

# Check LLM section in output
grep -c "AI Risk Analysis" data/reports/report_*.html

# Quick LLM endpoint test
curl http://localhost:8000/v1/models | jq .
```
```

**Step 2: Create `.vscode/settings.json`**

```json
{
  "cline.apiProvider": "openai",
  "cline.openAiBaseUrl": "http://localhost:8000/v1",
  "cline.openAiModelId": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-NVFP4",
  "cline.openAiApiKey": "trtllm",
  "cline.openAiStreamingEnabled": true,
  "cline.maxTokens": 8192,
  "editor.formatOnSave": true,
  "python.defaultInterpreterPath": "/home/peter-oakes/venvs/trtllm/bin/python"
}
```

**Step 3: Create `.mcp.json`**

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/home/peter-oakes/Desktop/LLMTestScripts"
      ]
    },
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    }
  }
}
```

**Step 4: Create docs directory and copy plan**

```bash
mkdir -p ~/Desktop/LLMTestScripts/docs/plans
```

**Step 5: Commit everything**

```bash
cd ~/Desktop/LLMTestScripts
git add .clinerules .vscode/ .mcp.json docs/
git commit -m "feat: add Cline config (.clinerules, .vscode/settings.json, .mcp.json)"
```

---

## Task 7: Push All Changes to GitHub

**Step 1: Verify all commits are local**

```bash
cd ~/Desktop/LLMTestScripts
git log --oneline
```

Expected output (5 commits):
```
abc1234 feat: add Cline config (.clinerules, .vscode/settings.json, .mcp.json)
def5678 feat: add LLM analysis section to HTML report
ghi9012 feat: wire LLMAnalyzer into report.py before report generation
jkl3456 feat: add llm_analysis config section
mno7890 feat: add src/llm package with LLMAnalyzer and prompt templates
pqr1234 feat: initial copy of trading-system base
```

**Step 2: Push to GitHub**

```bash
cd ~/Desktop/LLMTestScripts
git push origin main
```

**Step 3: Verify on GitHub**

```bash
gh repo view poakes28/LLMTestScripts --web
```

---

## Task 8: Verify End-to-End

**Step 1: Confirm Nemotron server is running**

```bash
curl http://localhost:8000/v1/models | jq .data[0].id
```
Expected: `"nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-NVFP4"`

**Step 2: Test LLM endpoint directly with a position prompt**

```bash
curl http://localhost:8000/v1/chat/completions \
  -s \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-NVFP4",
    "temperature": 0.6,
    "messages": [
      {"role": "system", "content": "You respond ONLY with valid JSON. No markdown."},
      {"role": "user", "content": "Return: {\"ticker\": \"AAPL\", \"risk_level\": \"medium\", \"signal\": \"HOLD\", \"signal_confidence\": 0.7, \"risk_factors\": [\"test\"], \"key_levels\": {\"support\": 180.0, \"resistance\": 200.0}, \"recommendation\": \"Hold.\", \"sentiment\": \"neutral\"}"}
    ],
    "chat_template_kwargs": {"thinking": false}
  }' | jq .choices[0].message.content
```

Expected: JSON string without `<think>` tags

**Step 3: Run report in preview mode**

```bash
cd ~/Desktop/LLMTestScripts
python scripts/report.py --preview --open
```

Expected log lines:
```
LLM analysis complete: N positions analyzed
Report saved to: data/reports/report_2026-03-16.html
Preview mode - email not sent
```

**Step 4: Verify LLM section in HTML**

```bash
grep -c "AI Risk Analysis" ~/Desktop/LLMTestScripts/data/reports/report_*.html
```
Expected: `1` or more

**Step 5: Test graceful degradation (stop Nemotron, run report)**

```bash
# Temporarily disable LLM in config
sed -i 's/enabled: true/enabled: false/' ~/Desktop/LLMTestScripts/config/settings.yaml
python scripts/report.py --preview
# Should complete without error, LLM section absent
# Re-enable
sed -i 's/enabled: false/enabled: true/' ~/Desktop/LLMTestScripts/config/settings.yaml
```
