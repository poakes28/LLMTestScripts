#!/usr/bin/env bash
# ============================================================================
# Linux/Ubuntu Cron Setup for Trading System
#
# Usage:
#   chmod +x scripts/setup_cron.sh
#   ./scripts/setup_cron.sh              # Install cron jobs
#   ./scripts/setup_cron.sh --remove     # Remove all trading cron jobs
#   ./scripts/setup_cron.sh --status     # Show installed jobs
# ============================================================================

set -euo pipefail

# --- Configuration (edit these) ---
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PROJECT_DIR}/venv/bin/python3"  # Use venv python
LOG_DIR="${PROJECT_DIR}/logs"
CRON_TAG="# TRADING_SYSTEM"

# Fall back to system python if no venv
if [ ! -f "$PYTHON_BIN" ]; then
    PYTHON_BIN="$(which python3)"
    echo "⚠  No venv found, using system python: $PYTHON_BIN"
fi

mkdir -p "$LOG_DIR"

# --- Functions ---
remove_existing() {
    echo "Removing existing trading system cron jobs..."
    crontab -l 2>/dev/null | grep -v "$CRON_TAG" | crontab - 2>/dev/null || true
    echo "✓ Cleared existing jobs"
}

show_status() {
    echo "Current trading system cron jobs:"
    echo "─────────────────────────────────"
    crontab -l 2>/dev/null | grep "$CRON_TAG" || echo "(none installed)"
}

install_crons() {
    remove_existing

    echo "Installing trading system cron jobs..."
    echo "  Project: $PROJECT_DIR"
    echo "  Python:  $PYTHON_BIN"
    echo ""

    # Build new crontab: preserve existing + add ours
    EXISTING=$(crontab -l 2>/dev/null || true)

    NEW_CRONS="
# ===== Trading Analysis System ===== ${CRON_TAG}
# Environment setup for cron context ${CRON_TAG}
SHELL=/bin/bash ${CRON_TAG}
PATH=/usr/local/bin:/usr/bin:/bin ${CRON_TAG}

# Morning Price Pull - 10:00 AM CT (Mon-Fri) ${CRON_TAG}
0 10 * * 1-5 cd ${PROJECT_DIR} && ${PYTHON_BIN} scripts/collect.py >> ${LOG_DIR}/cron_collect.log 2>&1 ${CRON_TAG}

# Midday Price Pull - 12:00 PM CT (Mon-Fri) ${CRON_TAG}
0 12 * * 1-5 cd ${PROJECT_DIR} && ${PYTHON_BIN} scripts/collect.py >> ${LOG_DIR}/cron_collect.log 2>&1 ${CRON_TAG}

# Closing Price Pull - 4:00 PM CT (Mon-Fri) ${CRON_TAG}
0 16 * * 1-5 cd ${PROJECT_DIR} && ${PYTHON_BIN} scripts/collect.py --update-paper >> ${LOG_DIR}/cron_collect.log 2>&1 ${CRON_TAG}

# Weekly Fundamentals Pull - Saturday 8:00 AM CT ${CRON_TAG}
0 8 * * 6 cd ${PROJECT_DIR} && ${PYTHON_BIN} scripts/collect.py --fundamentals >> ${LOG_DIR}/cron_fundamentals.log 2>&1 ${CRON_TAG}

# Analysis Engine - 5:00 PM CT (Mon-Fri) ${CRON_TAG}
0 17 * * 1-5 cd ${PROJECT_DIR} && ${PYTHON_BIN} scripts/analyze.py >> ${LOG_DIR}/cron_analysis.log 2>&1 ${CRON_TAG}

# Email Report - 6:00 AM CT (Mon-Fri) ${CRON_TAG}
0 6 * * 1-5 cd ${PROJECT_DIR} && ${PYTHON_BIN} scripts/report.py >> ${LOG_DIR}/cron_report.log 2>&1 ${CRON_TAG}

# Cron log rotation - Sunday midnight ${CRON_TAG}
0 0 * * 0 find ${LOG_DIR} -name 'cron_*.log' -mtime +30 -delete ${CRON_TAG}
# ===== End Trading System ===== ${CRON_TAG}
"

    echo "${EXISTING}${NEW_CRONS}" | crontab -
    echo ""
    echo "✓ Cron jobs installed. Schedule (Central Time):"
    echo "  10:00 AM  Mon-Fri  Price pull (morning)"
    echo "  12:00 PM  Mon-Fri  Price pull (midday)"
    echo "   4:00 PM  Mon-Fri  Price pull (closing + paper update)"
    echo "   5:00 PM  Mon-Fri  Analysis engine"
    echo "   6:00 AM  Mon-Fri  Email report"
    echo "   8:00 AM  Saturday Fundamentals pull"
    echo ""
    echo "⚠  IMPORTANT: Cron uses the system timezone."
    echo "   Verify with: timedatectl"
    echo "   Set to CT:   sudo timedatectl set-timezone America/Chicago"
}

# --- Main ---
case "${1:-install}" in
    --remove|-r)
        remove_existing
        ;;
    --status|-s)
        show_status
        ;;
    install|--install|*)
        install_crons
        show_status
        ;;
esac
