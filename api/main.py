"""
Trading System API — FastAPI application entry point.
Run with: uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 1 --reload
"""
import api.deps  # noqa — must be first: adds project root to sys.path

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routers import analysis, backtest, config, data, llm, portfolio, report, screener

app = FastAPI(
    title="Trading System API",
    version="2.0.0",
    description=(
        "REST API for the Trading Analysis System. "
        "Wraps technical/fundamental analysis, backtesting, stock screening, and LLM analysis."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS — permissive for LAN use; tighten origins in production if desired
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# API routers
# ---------------------------------------------------------------------------
app.include_router(screener.router, prefix="/api", tags=["Screener"])
app.include_router(llm.router, prefix="/api", tags=["LLM"])
app.include_router(backtest.router, prefix="/api", tags=["Backtest"])
app.include_router(analysis.router, prefix="/api", tags=["Analysis"])
app.include_router(config.router, prefix="/api", tags=["Config"])
app.include_router(data.router, prefix="/api", tags=["Data"])
app.include_router(portfolio.router, prefix="/api", tags=["Portfolio"])
app.include_router(report.router, prefix="/api", tags=["Report"])

# ---------------------------------------------------------------------------
# Static files — serve generated HTML reports
# ---------------------------------------------------------------------------
_project_root = Path(__file__).resolve().parent.parent
_reports_dir = _project_root / "data" / "reports"
_reports_dir.mkdir(parents=True, exist_ok=True)
app.mount("/reports", StaticFiles(directory=str(_reports_dir)), name="reports")

# ---------------------------------------------------------------------------
# Serve React PWA (production build) — mounted last so /api routes take priority
# ---------------------------------------------------------------------------
_dist_dir = _project_root / "app" / "dist"
if _dist_dir.exists():
    app.mount("/", StaticFiles(directory=str(_dist_dir), html=True), name="static")

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/api/health", tags=["System"])
async def health():
    """API health check."""
    return {"status": "ok", "version": "2.0.0"}


@app.get("/api/system", tags=["System"])
async def system_info():
    """Return basic system configuration."""
    try:
        from src.utils import load_config, get_all_tickers
        cfg = load_config()
        tickers = get_all_tickers()
        return {
            "system_name": cfg.get("system", {}).get("name", "Trading System"),
            "version": cfg.get("system", {}).get("version", "1.0.0"),
            "timezone": cfg.get("system", {}).get("timezone", "UTC"),
            "total_tickers": len(tickers),
            "funds": list(cfg.get("funds", {}).keys()),
            "llm_provider": cfg.get("llm", {}).get("provider", "claude"),
        }
    except Exception as e:
        return {"error": str(e)}
