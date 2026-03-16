# Trading Analysis System

A comprehensive Python trading analysis platform with three independent programs: **Data Collector**, **Analysis Engine**, and **Email Reporter**. Features three strategy funds, backtesting with slippage/commission modeling, paper trading, and automated scheduling for both Windows and Linux.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Data Collector  │────▶│  Analysis Engine  │────▶│  Email Reporter │
│                  │     │                  │     │                  │
│ • yfinance data  │     │ • Fundamental    │     │ • HTML reports   │
│ • Schwab sync    │     │ • Technical      │     │ • Equity curves  │
│ • Paper trades   │     │ • 3 Strategy     │     │ • Recommendations│
│ • Parquet store  │     │   Funds          │     │ • SMTP delivery  │
└─────────────────┘     │ • Backtesting    │     └─────────────────┘
                        └──────────────────┘
              ┌──────────────────────────────────┐
              │   Parquet Data Store (data/)      │
              │  prices / portfolios / analysis   │
              └──────────────────────────────────┘
```

## Strategy Funds

| Fund | Fundamental | Technical | Stop-Loss | Max Position | Max Sector |
|------|-------------|-----------|-----------|-------------|------------|
| **Fundamental Value** | 70% | 30% | 10% | 12% | 35% |
| **Technical Momentum** | 30% | 70% | 8% | 10% | 30% |
| **Balanced Hybrid** | 50% | 50% | 12% | 15% | 40% |

## Project Structure

```
trading-system/
├── config/
│   ├── settings.yaml          # Master config (funds, watchlist, risk params)
│   └── credentials.yaml       # API keys, email creds (DO NOT COMMIT)
├── data/
│   ├── prices/                # Daily & intraday price Parquet files
│   ├── portfolios/            # Paper portfolio state per fund
│   ├── analysis/              # Fundamentals cache, recommendations
│   ├── backtest/              # Equity curves, trade logs, summaries
│   └── reports/               # Generated HTML reports
├── src/
│   ├── utils.py               # Config loading, Parquet I/O, logging
│   ├── collector/
│   │   ├── price_fetcher.py   # yfinance data collection
│   │   ├── schwab_client.py   # Charles Schwab API (optional)
│   │   └── paper_portfolio.py # Paper trading portfolio manager
│   ├── analysis/
│   │   ├── technical.py       # RSI, MACD, Bollinger, support/resistance
│   │   ├── fundamental.py     # P/E, ROE, debt scoring
│   │   ├── risk_metrics.py    # Sharpe, Sortino, VaR, alpha/beta
│   │   └── strategies.py      # Combined signal generation per fund
│   ├── backtest/
│   │   └── engine.py          # Historical backtesting with slippage
│   └── reporting/
│       ├── report_generator.py # HTML report with embedded charts
│       └── email_sender.py     # SMTP email delivery
├── scripts/
│   ├── collect.py             # CLI: data collection
│   ├── analyze.py             # CLI: analysis & backtesting
│   ├── report.py              # CLI: report generation & email
│   ├── setup_scheduler.bat    # Windows Task Scheduler setup
│   ├── setup_cron.sh          # Linux cron setup
│   ├── setup_systemd.sh       # Linux systemd timer setup
│   └── setup_linux.sh         # Linux first-time environment setup
├── logs/                      # Rotating daily log files
├── requirements.txt
└── README.md
```

---

## Setup

### Linux/Ubuntu

```bash
git clone <repo> && cd trading-system
chmod +x scripts/*.sh
./scripts/setup_linux.sh
```

This creates a venv, installs all dependencies, sets up directories, and validates config.

### Windows

```powershell
cd trading-system
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Configure

1. **Edit `config/settings.yaml`** — adjust watchlist, fund parameters, risk settings
2. **Edit `config/credentials.yaml`** — add Schwab API keys and/or Gmail app password
3. **Add to `.gitignore`**: `config/credentials.yaml`, `data/`, `logs/`

---

## Usage

### 1. Collect Data

```bash
# First run: fetch 2 years of historical data
python scripts/collect.py --historical

# Fetch fundamental data (P/E, ROE, etc.)
python scripts/collect.py --fundamentals

# Regular price pull (run 3x daily)
python scripts/collect.py

# Sync real Schwab portfolio (if configured)
python scripts/collect.py --sync
```

### 2. Run Analysis

```bash
# Full analysis across all funds
python scripts/analyze.py

# Analyze specific fund
python scripts/analyze.py --fund technical

# Run backtests
python scripts/analyze.py --backtest
python scripts/analyze.py --backtest --fund balanced --start 2023-01-01 --end 2025-01-01
```

### 3. Generate Reports

```bash
# Preview report (save locally, no email)
python scripts/report.py --preview --open

# Generate and send email
python scripts/report.py

# Custom output path
python scripts/report.py --preview --output /tmp/report.html
```

---

## Scheduling

### Daily Schedule (all times Central)

| Time | Task | Script |
|------|------|--------|
| 6:00 AM | Email morning report | `report.py` |
| 10:00 AM | Morning price pull | `collect.py` |
| 12:00 PM | Midday price pull | `collect.py` |
| 4:00 PM | Closing prices + paper update | `collect.py --update-paper` |
| 5:00 PM | Run analysis engine | `analyze.py` |
| Sat 8 AM | Weekly fundamentals | `collect.py --fundamentals` |

### Linux — Option A: Cron (simple)

```bash
./scripts/setup_cron.sh            # Install cron jobs
./scripts/setup_cron.sh --status   # Check status
./scripts/setup_cron.sh --remove   # Remove jobs
```

### Linux — Option B: Systemd Timers (robust)

```bash
sudo ./scripts/setup_systemd.sh            # Install & enable timers
sudo ./scripts/setup_systemd.sh --status   # Check status
sudo ./scripts/setup_systemd.sh --remove   # Remove timers

# View logs
journalctl -u trading-analysis.service --since today

# Manually trigger a run
sudo systemctl start trading-collect-morning.service
```

**Systemd advantages over cron:** catches up on missed runs (`Persistent=true`), better logging via `journalctl`, resource limits (CPU/memory caps), and dependency management.

### Windows — Task Scheduler

```cmd
# Run as Administrator
scripts\setup_scheduler.bat
```

### Timezone

The schedule assumes **America/Chicago (Central Time)**. On Linux:

```bash
# Check current timezone
timedatectl

# Set to Central Time
sudo timedatectl set-timezone America/Chicago
```

---

## Backtesting

The backtest engine simulates strategy execution on historical data with realistic conditions:

- **Slippage**: 0.1% per trade (configurable)
- **Commissions**: Modeled even at $0 base (0.01% per trade value)
- **Stop-loss triggers**: Fixed and trailing stops checked daily
- **Take-profit triggers**: Auto-close at target price
- **Position sizing**: 2% max risk per trade, Kelly criterion optional
- **Benchmark**: SPY comparison with alpha/beta calculation

### Output Metrics

Sharpe ratio, Sortino ratio, Calmar ratio, max drawdown, VaR (95%/99%), alpha, beta, win rate, profit factor, expectancy, and full equity curve.

---

## Cross-Platform Notes

All Python source code is fully cross-platform. The only platform-specific files are the scheduling scripts:

| Component | Windows | Linux |
|-----------|---------|-------|
| Scheduler | `setup_scheduler.bat` | `setup_cron.sh` or `setup_systemd.sh` |
| Python path | Full path to `python.exe` | `venv/bin/python3` |
| Env setup | Manual venv creation | `setup_linux.sh` (automated) |
| Log viewing | File explorer | `journalctl` or `tail -f logs/` |
| Timezone | Windows Settings | `timedatectl` |

The Parquet data files, YAML configs, and all analysis output work identically on both platforms.

---

## Dependencies

```
pandas, numpy, yfinance, pandas-ta, pyarrow, matplotlib,
plotly, jinja2, pyyaml, loguru, schedule, requests, scipy
```

## License

For personal use. Not financial advice — past performance does not guarantee future results.
