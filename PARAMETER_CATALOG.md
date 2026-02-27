# Trading System — Variable Input Parameter Catalog

**Purpose:** Check the boxes next to the parameters you want controllable in your mobile app.
After marking up this file, return it and the app scaffold will be built around your selections.

**How to use:** Replace `- [ ]` with `- [x]` for any parameter you want in the app.

---

## Section 1 — Watchlist & Tickers
*What stocks the system tracks and analyzes*

**Current lists:**
- Core (20): AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, JPM, V, JNJ, UNH, PG, HD, MA, XOM, LLY, AVGO, COST, PEP, ABBV
- Sector ETFs (12): SPY, QQQ, XLF, XLK, XLV, XLE, XLI, XLY, XLP, XLU, XLRE, XLB
- Radar (10): AMD, CRM, NFLX, DIS, PYPL, SQ, SHOP, SNOW, PLTR, COIN

| # | Select | Parameter | Current Default | UI Type | What It Changes |
|---|--------|-----------|----------------|---------|-----------------|
| 1.1 | - [X] | Core watchlist — add/remove tickers | 20 stocks | multi-select / text input | Which stocks get full analysis and paper trading |
| 1.2 | - [X] | Radar watchlist — add/remove tickers | 10 stocks | multi-select / text input | Speculative/high-growth candidates tracked separately |
| 1.3 | - [X] | ETF watchlist — add/remove tickers | 12 ETFs | multi-select / text input | Sector benchmark ETFs used for context |
| 1.4 | - [ ] | Run analysis on specific ticker(s) only | All 42 | multi-select | Ad-hoc deep-dive on selected symbols |

---

## Section 2 — Data Collection
*Controls how market data is fetched from yfinance*

| # | Select | Parameter | Current Default | UI Type | What It Changes |
|---|--------|-----------|----------------|---------|-----------------|
| 2.1 | - [X] | Historical price period | 2y | dropdown: 3mo / 6mo / 1y / 2y / 5y | How far back OHLCV history goes when refreshing |
| 2.2 | - [X] | Price bar interval | 1d (daily) | dropdown: 1d / 1wk | Daily vs weekly price bars |
| 2.3 | - [X] | Trigger manual price refresh | — | button | Fetches current prices immediately on demand |
| 2.4 | - [X] | Trigger historical data re-pull | — | button | Re-downloads full history (slower) |
| 2.5 | - [X] | Trigger fundamentals refresh | — | button | Re-fetches P/E, ROE, balance sheet data |
| 2.6 | - [X] | API batch size | 10 tickers | number (1–20) | How many tickers fetched per yfinance call |
| 2.7 | - [X] | Max retries on API failure | 3 | number (1–10) | Resilience of data fetching |

---

## Section 3 — Technical Indicator Parameters
*Controls how indicators are calculated in `src/analysis/technical.py`*
*Changing these changes every BUY/SELL/HOLD signal — these are the core "tuning knobs"*

### Moving Averages
| # | Select | Parameter | Current Default | UI Type | What It Changes |
|---|--------|-----------|----------------|---------|-----------------|
| 3.1 | - [X] | SMA short period | 20 bars | slider: 5–50 | Short-term trend line crossover signals |
| 3.2 | - [X] | SMA long period | 50 bars | slider: 20–150 | Medium-term trend confirmation |
| 3.3 | - [X] | SMA trend period | 200 bars | slider: 100–300 | Long-term bull/bear direction filter |

### RSI (Relative Strength Index) — Momentum Oscillator
| # | Select | Parameter | Current Default | UI Type | What It Changes |
|---|--------|-----------|----------------|---------|-----------------|
| 3.4 | - [X] | RSI calculation period | 14 bars | slider: 5–30 | How sensitive RSI is to recent moves (lower = faster) |
| 3.5 | - [X] | RSI oversold level (buy zone) | 30 | slider: 10–45 | Below this = stock considered oversold → buy signal |
| 3.6 | - [X] | RSI overbought level (sell zone) | 70 | slider: 55–90 | Above this = stock considered overbought → sell signal |

### MACD (Moving Average Convergence Divergence)
| # | Select | Parameter | Current Default | UI Type | What It Changes |
|---|--------|-----------|----------------|---------|-----------------|
| 3.7 | - [X] | MACD fast EMA period | 12 bars | slider: 5–20 | Fast component of MACD line |
| 3.8 | - [X] | MACD slow EMA period | 26 bars | slider: 15–50 | Slow component of MACD line |
| 3.9 | - [X] | MACD signal line period | 9 bars | slider: 3–20 | Trigger line for MACD crossover signals |

### Bollinger Bands — Volatility Channels
| # | Select | Parameter | Current Default | UI Type | What It Changes |
|---|--------|-----------|----------------|---------|-----------------|
| 3.10 | - [X] | Bollinger band period | 20 bars | slider: 10–50 | Middle band (SMA) for Bollinger Bands |
| 3.11 | - [X] | Bollinger band width (std dev) | 2.0 | slider: 1.0–3.5, step 0.25 | Wider bands = fewer signals, tighter = more |

### Volatility & Volume
| # | Select | Parameter | Current Default | UI Type | What It Changes |
|---|--------|-----------|----------------|---------|-----------------|
| 3.12 | - [X] | ATR (Average True Range) period | 14 bars | slider: 5–30 | Volatility measurement used in stop-loss pricing |
| 3.13 | - [X] | Volume average period | 20 bars | slider: 5–50 | Baseline for detecting above/below average volume |

### Support & Resistance Detection
| # | Select | Parameter | Current Default | UI Type | What It Changes |
|---|--------|-----------|----------------|---------|-----------------|
| 3.14 | - [X] | S/R lookback window | 20 bars | slider: 10–60 | How far back to scan for local price extremes |
| 3.15 | - [X] | Min touches to confirm level | 2 touches | slider: 1–5 | How many times price must test a level to call it S/R |

---

## Section 4 — Fundamental Screening Criteria
*Thresholds used to score and filter stocks in `src/analysis/fundamental.py`*
*Each criterion contributes to a 0–100 composite score that drives BUY/SELL/HOLD*

### Valuation (30 pts max)
| # | Select | Parameter | Current Default | UI Type | What It Changes |
|---|--------|-----------|----------------|---------|-----------------|
| 4.1 | - [X] | P/E ratio maximum | 25× | slider: 5–75 | Stocks above this earn 0 valuation points |
| 4.2 | - [X] | PEG ratio maximum | 2.0× | slider: 0.5–5.0, step 0.25 | Growth-adjusted P/E ceiling |

### Profitability (25 pts max)
| # | Select | Parameter | Current Default | UI Type | What It Changes |
|---|--------|-----------|----------------|---------|-----------------|
| 4.3 | - [X] | ROE minimum | 12% | slider: 0–40% | Return on Equity floor — filters out low-profit companies |
| 4.4 | - [X] | ROA minimum | 5% | slider: 0–20% | Return on Assets floor — asset efficiency filter |
| 4.5 | - [X] | Profit margin minimum | 10% | slider: 0–40% | Net profit margin floor |

### Growth (20 pts max)
| # | Select | Parameter | Current Default | UI Type | What It Changes |
|---|--------|-----------|----------------|---------|-----------------|
| 4.6 | - [X] | Revenue growth minimum | 5% YoY | slider: 0–50% | Removes stagnant/declining companies |
| 4.7 | - [X] | Earnings growth minimum | 5% YoY | slider: 0–50% | EPS growth floor |

### Financial Health (15 pts max)
| # | Select | Parameter | Current Default | UI Type | What It Changes |
|---|--------|-----------|----------------|---------|-----------------|
| 4.8 | - [X] | Debt/Equity maximum | 1.5× | slider: 0–6.0, step 0.25 | Debt load ceiling — higher = more leveraged allowed |
| 4.9 | - [X] | Current ratio minimum | 1.2× | slider: 0.5–3.0, step 0.1 | Short-term liquidity floor |
| 4.10 | - [X] | Quick ratio minimum | 0.8× | slider: 0.3–2.0, step 0.1 | Tighter liquidity floor (excludes inventory) |

### Quality (10 pts max)
| # | Select | Parameter | Current Default | UI Type | What It Changes |
|---|--------|-----------|----------------|---------|-----------------|
| 4.11 | - [X] | Free cash flow yield minimum | 3% | slider: 0–10% | Quality filter — real cash generation |
| 4.12 | - [X] | Dividend yield minimum | 0% | slider: 0–8% | Income filter (0 = no dividend requirement) |

---

## Section 5 — Fund Strategy Weights
*How much each signal type (technical vs. fundamental) counts per fund*
*In `src/analysis/strategies.py` — drives composite BUY/SELL/HOLD scores*

### Fundamental Value Fund (currently: 70% fundamental, 30% technical)
| # | Select | Parameter | Current Default | UI Type | What It Changes |
|---|--------|-----------|----------------|---------|-----------------|
| 5.1 | - [X] | Fundamental signal weight | 70% | slider: 0–100% | How much P/E, ROE, margins count vs price action |
| 5.2 | - [X] | Technical signal weight | 30% | slider: auto-complement | How much RSI, MACD, MAs count |
| 5.3 | - [X] | Composite BUY threshold | 0.15 | slider: 0.05–0.50 | Score must exceed this to generate a BUY |
| 5.4 | - [X] | Composite SELL threshold | −0.15 | slider: −0.50–−0.05 | Score must fall below this to generate a SELL |

### Technical Momentum Fund (currently: 30% fundamental, 70% technical)
| # | Select | Parameter | Current Default | UI Type | What It Changes |
|---|--------|-----------|----------------|---------|-----------------|
| 5.5 | - [X] | Fundamental signal weight | 30% | slider: 0–100% | How much fundamentals count vs price action |
| 5.6 | - [X] | Technical signal weight | 70% | slider: auto-complement | How much RSI, MACD, MAs count |
| 5.7 | - [X] | Composite BUY threshold | 0.15 | slider: 0.05–0.50 | Score must exceed this to generate a BUY |
| 5.8 | - [X] | Composite SELL threshold | −0.15 | slider: −0.50–−0.05 | Score must fall below this to generate a SELL |

### Balanced Hybrid Fund (currently: 50% / 50%)
| # | Select | Parameter | Current Default | UI Type | What It Changes |
|---|--------|-----------|----------------|---------|-----------------|
| 5.9 | - [X] | Fundamental signal weight | 50% | slider: 0–100% | Equal blend — raise/lower to tilt the blend |
| 5.10 | - [X] | Technical signal weight | 50% | slider: auto-complement | How much price action counts |
| 5.11 | - [X] | Composite BUY threshold | 0.15 | slider: 0.05–0.50 | Score must exceed this to generate a BUY |
| 5.12 | - [X] | Composite SELL threshold | −0.15 | slider: −0.50–−0.05 | Score must fall below this to generate a SELL |

---

## Section 6 — Risk Management (per fund)
*Position sizing, stop-losses, and sector limits in `config/settings.yaml` → fund.risk_params*

### Fundamental Value Fund
| # | Select | Parameter | Current Default | UI Type | What It Changes |
|---|--------|-----------|----------------|---------|-----------------|
| 6.1 | - [X] | Stop loss % | 10% | slider: 2–25% | Fixed exit if position drops this much |
| 6.2 | - [X] | Trailing stop % | 8% | slider: 2–20% | Dynamic stop that tracks highest price |
| 6.3 | - [X] | Max single position size | 12% | slider: 2–25% | Maximum % of fund in one stock |
| 6.4 | - [X] | Max sector allocation | 35% | slider: 10–60% | Maximum % of fund in one sector |
| 6.5 | - [X] | Max risk per trade | 2% | slider: 0.5–5% | Max capital at risk on any single trade |
| 6.6 | - [X] | Kelly criterion | Off | toggle | Use Kelly formula for position sizing |
| 6.7 | - [X] | Kelly fraction | 0.25 | slider: 0.1–1.0 | Fraction of Kelly to use (1.0 = full Kelly) |

### Technical Momentum Fund
| # | Select | Parameter | Current Default | UI Type | What It Changes |
|---|--------|-----------|----------------|---------|-----------------|
| 6.8 | - [X] | Stop loss % | 8% | slider: 2–25% | Fixed exit threshold |
| 6.9 | - [X] | Trailing stop % | 6% | slider: 2–20% | Trailing exit threshold |
| 6.10 | - [X] | Max single position size | 10% | slider: 2–25% | Max % per stock |
| 6.11 | - [X] | Max sector allocation | 30% | slider: 10–60% | Max % per sector |
| 6.12 | - [X] | Max risk per trade | 2% | slider: 0.5–5% | Capital at risk per trade |
| 6.13 | - [X] | Kelly criterion | On | toggle | Use Kelly formula for position sizing |
| 6.14 | - [X] | Kelly fraction | 0.25 | slider: 0.1–1.0 | Fraction of Kelly to use |

### Balanced Hybrid Fund
| # | Select | Parameter | Current Default | UI Type | What It Changes |
|---|--------|-----------|----------------|---------|-----------------|
| 6.15 | - [X] | Stop loss % | 12% | slider: 2–25% | Fixed exit threshold |
| 6.16 | - [X] | Trailing stop % | 10% | slider: 2–20% | Trailing exit threshold |
| 6.17 | - [X] | Max single position size | 15% | slider: 2–25% | Max % per stock |
| 6.18 | - [X] | Max sector allocation | 40% | slider: 10–60% | Max % per sector |
| 6.19 | - [X] | Max risk per trade | 2% | slider: 0.5–5% | Capital at risk per trade |
| 6.20 | - [X] | Kelly criterion | Off | toggle | Use Kelly formula for position sizing |
| 6.21 | - [X] | Kelly fraction | 0.25 | slider: 0.1–1.0 | Fraction of Kelly to use |

---

## Section 7 — Backtest Parameters
*Controls historical simulation in `src/backtest/engine.py`*

| # | Select | Parameter | Current Default | UI Type | What It Changes |
|---|--------|-----------|----------------|---------|-----------------|
| 7.1 | - [X] | Backtest start date | 2023-01-01 | date picker | Beginning of simulation window |
| 7.2 | - [X] | Backtest end date | 2025-01-01 | date picker | End of simulation window |
| 7.3 | - [X] | Initial capital | $100,000 | number input | Starting portfolio value |
| 7.4 | - [X] | Fund to backtest | All 3 funds | dropdown / multi-select | Which fund(s) to run |
| 7.5 | - [X] | Tickers to include | Top 20 by score | multi-select | Limit backtest to specific symbols |
| 7.6 | - [X] | Slippage % | 0.1% | slider: 0–1%, step 0.05% | Simulated fill cost per trade |
| 7.7 | - [X] | Commission % | 0.01% | slider: 0–0.5%, step 0.01% | % cost per trade |
| 7.8 | - [X] | Commission flat fee | $0 | number | Fixed dollar cost per trade |
| 7.9 | - [X] | Benchmark ticker | SPY | text / dropdown | Index to compare results against |
| 7.10 | - [X] | Risk-free rate | 5% | slider: 0–10%, step 0.25% | Baseline for Sharpe/Sortino ratio calculation |
| 7.11 | - [X] | Min days between trades | 1 day | slider: 1–30 days | Prevents over-trading the same symbol |
| 7.12 | - [X] | Signal re-evaluation cadence | Every 5 days | slider: 1–30 days | How often new signals are generated during backtest |
| 7.13 | - [X] | Trigger backtest run | — | button | Runs backtest with current parameters on demand |

---

## Section 8 — Report & Output Controls
*What the HTML report shows; in `src/reporting/report_generator.py`*

| # | Select | Parameter | Current Default | UI Type | What It Changes |
|---|--------|-----------|----------------|---------|-----------------|
| 8.1 | - [X] | Max recommendations per fund | 10 | slider: 3–25 | How many top buys/sells appear in the report |
| 8.2 | - [X] | Funds shown in report | All 3 | multi-select toggles | Include/exclude individual funds from output |
| 8.3 | - [X] | Include equity curve chart | Yes | toggle | Show/hide backtest equity curve PNG |
| 8.4 | - [X] | Include sector allocation chart | Yes | toggle | Show/hide pie chart of portfolio allocation |
| 8.5 | - [X] | Generate report on demand | — | button | Triggers report regeneration immediately |
| 8.6 | - [X] | Open report in browser | — | button | Opens current report in browser |
| 8.7 | - [X] | Email report enabled | Off | toggle | Sends email after generation (requires credentials) |
| 8.8 | - [X] | Email recipients | (empty) | text list | Who receives the report |

---

## Section 9 — On-Demand Analysis Actions
*Trigger existing analysis functions directly from the app*

| # | Select | Parameter | Current Default | UI Type | What It Runs |
|---|--------|-----------|----------------|---------|--------------|
| 9.1 | - [X] | Run full analysis (all funds) | — | button | `scripts/analyze.py` — all 3 funds |
| 9.2 | - [X] | Run analysis for specific fund | — | dropdown + button | `scripts/analyze.py --fund [name]` |
| 9.3 | - [X] | View top BUY signals | 10 results | number + button | `get_top_buys(fund, n)` |
| 9.4 | - [X] | View top SELL signals | 10 results | number + button | `get_top_sells(fund, n)` |
| 9.5 | - [X] | Look up single ticker signal | — | text input + button | Full technical + fundamental score for one symbol |
| 9.6 | - [X] | View support/resistance levels | — | text input + button | `find_support_resistance()` for one ticker |
| 9.7 | - [X] | View current paper portfolio | — | button | All 3 funds' positions and P&L |
| 9.8 | - [X] | View risk metrics dashboard | — | button | Sharpe, Sortino, Max Drawdown, Alpha, Beta |
| 9.9 | - [X] | Run backtest with current params | — | button | Triggers full backtest run |

---

## Summary Count

| Section | Parameters | Selectable Items |
|---------|-----------|-----------------|
| 1 — Watchlist & Tickers | 4 | Ticker lists and ad-hoc analysis |
| 2 — Data Collection | 7 | Fetch controls and triggers |
| 3 — Technical Indicators | 15 | All indicator tuning knobs |
| 4 — Fundamental Criteria | 12 | All scoring thresholds |
| 5 — Fund Strategy Weights | 12 | Per-fund blending controls |
| 6 — Risk Management | 21 | Per-fund risk params |
| 7 — Backtest Parameters | 13 | Full backtest control |
| 8 — Report Controls | 8 | Output and delivery |
| 9 — On-Demand Actions | 9 | Direct function triggers |
| **TOTAL** | **101** | |

---

## Notes for App Architecture

Once you return your selections, the app will be built as:

**Backend:** FastAPI (Python) running on your Linux machine — wraps the existing trading system
modules with no changes to any current code.

**Frontend:** Progressive Web App (PWA) — runs in your phone's browser, installable as a home
screen icon, no app store required. Connects to your machine over your home WiFi (or remotely via
Tailscale/VPN).

**Each checked parameter becomes a UI control** (slider, toggle, date picker, etc.) that hits an
API endpoint, which updates `config/settings.yaml` and/or passes parameters directly to the
analysis/backtest functions.

---

*Generated: 2026-02-26 | Source: Trading System - Opus 4.6*
