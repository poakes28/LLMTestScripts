#!/usr/bin/env bash
# ============================================================================
# Linux/Ubuntu First-Time Setup for Trading System
#
# Creates venv, installs dependencies, sets permissions, validates config.
#
# Usage:
#   chmod +x scripts/setup_linux.sh
#   ./scripts/setup_linux.sh
# ============================================================================

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo "============================================"
echo "  Trading System - Linux Setup"
echo "============================================"
echo "Project directory: $PROJECT_DIR"
echo ""

# --- Check Python ---
PYTHON_MIN="3.10"
if ! command -v python3 &>/dev/null; then
    echo "❌ python3 not found. Install with:"
    echo "   sudo apt update && sudo apt install python3 python3-pip python3-venv"
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✓ Python ${PY_VERSION} found"

# --- Create virtual environment ---
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✓ venv created"
else
    echo "✓ venv already exists"
fi

source venv/bin/activate

# --- Install dependencies ---
echo "Installing Python dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✓ Dependencies installed"

# --- Create directories ---
echo "Creating data directories..."
mkdir -p data/{prices,portfolios,analysis,backtest,reports}
mkdir -p logs
echo "✓ Directories created"

# --- Set script permissions ---
echo "Setting executable permissions..."
chmod +x scripts/*.sh scripts/*.py 2>/dev/null || true
echo "✓ Permissions set"

# --- Validate config ---
echo "Validating configuration..."
python3 -c "
import yaml
with open('config/settings.yaml') as f:
    cfg = yaml.safe_load(f)
funds = list(cfg.get('funds', {}).keys())
tickers = sum(len(v) for v in cfg.get('watchlist', {}).values() if isinstance(v, list))
print(f'  Funds configured: {funds}')
print(f'  Watchlist tickers: {tickers}')
print(f'  Email enabled: {cfg.get(\"email\", {}).get(\"enabled\", False)}')
"
echo "✓ Config valid"

# --- Check credentials ---
if [ -f "config/credentials.yaml" ]; then
    HAS_CREDS=$(python3 -c "
import yaml
with open('config/credentials.yaml') as f:
    c = yaml.safe_load(f)
email = c.get('email', {}).get('sender_email', '')
schwab = c.get('schwab', {}).get('app_key', '')
print('email' if email else '', 'schwab' if schwab else '')
")
    if echo "$HAS_CREDS" | grep -q "email"; then
        echo "✓ Email credentials configured"
    else
        echo "⚠  Email credentials not set (edit config/credentials.yaml)"
    fi
    if echo "$HAS_CREDS" | grep -q "schwab"; then
        echo "✓ Schwab credentials configured"
    else
        echo "ℹ  Schwab API not configured (paper trading only)"
    fi
else
    echo "⚠  No credentials.yaml found"
fi

# --- Set timezone reminder ---
CURRENT_TZ=$(timedatectl 2>/dev/null | grep "Time zone" | awk '{print $3}' || echo "unknown")
echo ""
echo "Current timezone: $CURRENT_TZ"
if [ "$CURRENT_TZ" != "America/Chicago" ]; then
    echo "⚠  Scheduler times assume Central Time. To set:"
    echo "   sudo timedatectl set-timezone America/Chicago"
fi

# --- Summary ---
echo ""
echo "============================================"
echo "  Setup Complete!"
echo "============================================"
echo ""
echo "Quick start:"
echo "  source venv/bin/activate"
echo ""
echo "  # 1. Fetch initial data"
echo "  python scripts/collect.py --historical"
echo "  python scripts/collect.py --fundamentals"
echo ""
echo "  # 2. Run analysis"
echo "  python scripts/analyze.py"
echo ""
echo "  # 3. Run backtest"
echo "  python scripts/analyze.py --backtest"
echo ""
echo "  # 4. Generate report"
echo "  python scripts/report.py --preview --open"
echo ""
echo "Scheduling (choose one):"
echo "  ./scripts/setup_cron.sh          # Simple cron jobs"
echo "  sudo ./scripts/setup_systemd.sh  # Robust systemd timers"
echo ""
echo "⚠  Add config/credentials.yaml to .gitignore!"
