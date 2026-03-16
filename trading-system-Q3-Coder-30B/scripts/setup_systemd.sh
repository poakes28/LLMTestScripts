#!/usr/bin/env bash
# ============================================================================
# Systemd Timer Setup for Trading System (alternative to cron)
#
# Systemd timers are more robust than cron — they handle missed runs,
# have better logging (journalctl), and integrate with system monitoring.
#
# Usage:
#   sudo ./scripts/setup_systemd.sh              # Install & enable
#   sudo ./scripts/setup_systemd.sh --remove     # Remove all units
#   sudo ./scripts/setup_systemd.sh --status     # Show timer status
# ============================================================================

set -euo pipefail

# --- Configuration ---
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PROJECT_DIR}/venv/bin/python3"
RUN_USER="${SUDO_USER:-$(whoami)}"
UNIT_DIR="/etc/systemd/system"

if [ ! -f "$PYTHON_BIN" ]; then
    PYTHON_BIN="$(which python3)"
fi

# --- Helpers ---
create_service() {
    local name="$1"
    local description="$2"
    local exec_cmd="$3"

    cat > "${UNIT_DIR}/trading-${name}.service" <<EOF
[Unit]
Description=Trading System - ${description}
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=${RUN_USER}
WorkingDirectory=${PROJECT_DIR}
ExecStart=${exec_cmd}
StandardOutput=append:${PROJECT_DIR}/logs/systemd_${name}.log
StandardError=append:${PROJECT_DIR}/logs/systemd_${name}.log
Environment=PYTHONUNBUFFERED=1

# Restart on failure with backoff
Restart=on-failure
RestartSec=30

# Resource limits
MemoryMax=2G
CPUQuota=80%
EOF
}

create_timer() {
    local name="$1"
    local description="$2"
    local on_calendar="$3"
    local persistent="$4"

    cat > "${UNIT_DIR}/trading-${name}.timer" <<EOF
[Unit]
Description=Trading System Timer - ${description}

[Timer]
OnCalendar=${on_calendar}
Persistent=${persistent}
AccuracySec=1min
RandomizedDelaySec=30

[Install]
WantedBy=timers.target
EOF
}

install_units() {
    echo "Installing systemd units for Trading System..."
    echo "  Project: ${PROJECT_DIR}"
    echo "  User:    ${RUN_USER}"
    echo "  Python:  ${PYTHON_BIN}"
    echo ""

    mkdir -p "${PROJECT_DIR}/logs"

    # --- Price Pull Morning (10:00 AM Mon-Fri) ---
    create_service "collect-morning" "Morning Price Pull" \
        "${PYTHON_BIN} ${PROJECT_DIR}/scripts/collect.py"
    create_timer "collect-morning" "Morning Price Pull" \
        "Mon..Fri *-*-* 10:00:00" "true"

    # --- Price Pull Midday (12:00 PM Mon-Fri) ---
    create_service "collect-midday" "Midday Price Pull" \
        "${PYTHON_BIN} ${PROJECT_DIR}/scripts/collect.py"
    create_timer "collect-midday" "Midday Price Pull" \
        "Mon..Fri *-*-* 12:00:00" "true"

    # --- Price Pull Closing (4:00 PM Mon-Fri) ---
    create_service "collect-closing" "Closing Price Pull" \
        "${PYTHON_BIN} ${PROJECT_DIR}/scripts/collect.py --update-paper"
    create_timer "collect-closing" "Closing Price Pull" \
        "Mon..Fri *-*-* 16:00:00" "true"

    # --- Fundamentals (Saturday 8:00 AM) ---
    create_service "fundamentals" "Weekly Fundamentals Pull" \
        "${PYTHON_BIN} ${PROJECT_DIR}/scripts/collect.py --fundamentals"
    create_timer "fundamentals" "Weekly Fundamentals Pull" \
        "Sat *-*-* 08:00:00" "true"

    # --- Analysis Engine (5:00 PM Mon-Fri) ---
    create_service "analysis" "Analysis Engine" \
        "${PYTHON_BIN} ${PROJECT_DIR}/scripts/analyze.py"
    create_timer "analysis" "Analysis Engine" \
        "Mon..Fri *-*-* 17:00:00" "true"

    # --- Email Report (6:00 AM Mon-Fri) ---
    create_service "report" "Email Report" \
        "${PYTHON_BIN} ${PROJECT_DIR}/scripts/report.py"
    create_timer "report" "Email Report" \
        "Mon..Fri *-*-* 06:00:00" "true"

    # Reload and enable
    systemctl daemon-reload

    for timer in collect-morning collect-midday collect-closing fundamentals analysis report; do
        systemctl enable "trading-${timer}.timer"
        systemctl start "trading-${timer}.timer"
    done

    echo ""
    echo "✓ All systemd timers installed and enabled."
    echo ""
    show_status
}

remove_units() {
    echo "Removing trading system systemd units..."
    for timer in collect-morning collect-midday collect-closing fundamentals analysis report; do
        systemctl stop "trading-${timer}.timer" 2>/dev/null || true
        systemctl disable "trading-${timer}.timer" 2>/dev/null || true
        rm -f "${UNIT_DIR}/trading-${timer}.service"
        rm -f "${UNIT_DIR}/trading-${timer}.timer"
    done
    systemctl daemon-reload
    echo "✓ All trading system units removed"
}

show_status() {
    echo "Trading System Timer Status:"
    echo "───────────────────────────────────────────────────────────"
    systemctl list-timers 'trading-*' --no-pager 2>/dev/null || echo "(no timers found)"
    echo ""
    echo "View logs:  journalctl -u trading-analysis.service --since today"
    echo "Test run:   systemctl start trading-collect-morning.service"
}

# --- Main ---
if [ "$(id -u)" -ne 0 ] && [ "${1:-}" != "--status" ]; then
    echo "Error: Run with sudo for install/remove operations"
    echo "Usage: sudo $0 [--install|--remove|--status]"
    exit 1
fi

case "${1:-install}" in
    --remove|-r)   remove_units ;;
    --status|-s)   show_status ;;
    install|*)     install_units ;;
esac
