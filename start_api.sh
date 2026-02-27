#!/bin/bash
# Trading System — production launcher
# Usage:
#   ./start_api.sh              # with hot-reload (dev)
#   ./start_api.sh --no-reload  # production (faster, stable)
#
# The React PWA is built into app/dist/ and served at the root URL.
# To rebuild after UI changes: cd app && npm run build
#
# For live frontend development (hot module replacement):
#   Terminal 1: ./start_api.sh --no-reload   (backend)
#   Terminal 2: cd app && npm run dev         (frontend dev server on :5173)

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

source venv/bin/activate

LOCAL_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "  Trading System"
echo "  ──────────────────────────────────────────────────"
echo "  API Docs:  http://localhost:8000/docs"
echo "  App:       http://localhost:8000"
echo "  Phone:     http://${LOCAL_IP}:8000      (same WiFi)"
echo "  ──────────────────────────────────────────────────"
echo ""

if [[ "$1" == "--no-reload" ]]; then
    uvicorn api.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --workers 1 \
        --log-level info
else
    uvicorn api.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --workers 1 \
        --log-level info \
        --reload
fi
