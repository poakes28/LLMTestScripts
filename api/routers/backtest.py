"""
Backtest endpoints.
- /backtest/strategy: wraps existing BacktestEngine.run_backtest() (unchanged)
- /backtest/screen: uses new run_screen_backtest() added in Phase 3
"""
from typing import Dict
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException

import api.deps  # noqa
from api.models.backtest import BacktestJobStatus, ScreenBacktestRequest, StrategyBacktestRequest

router = APIRouter()

_jobs: Dict[str, Dict] = {}


def _serialize_backtest_result(result: Dict) -> Dict:
    """Convert DataFrames and numpy types in backtest result to JSON-safe types."""
    import math
    import numpy as np
    import pandas as pd

    def _clean(obj):
        if isinstance(obj, pd.DataFrame):
            records = obj.to_dict("records")
            return [{k: _clean(v) for k, v in r.items()} for r in records]
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            v = float(obj)
            return None if math.isnan(v) else v
        if isinstance(obj, float) and math.isnan(obj):
            return None
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_clean(i) for i in obj]
        return obj

    return _clean(result)


def _run_strategy_backtest(job_id: str, request: StrategyBacktestRequest):
    try:
        from src.backtest.engine import BacktestEngine
        engine = BacktestEngine()
        result = engine.run_backtest(
            fund_name=request.fund_name,
            start_date=request.start_date,
            end_date=request.end_date,
            tickers=request.tickers,
            initial_capital=request.initial_capital,
        )
        _jobs[job_id]["status"] = "complete"
        _jobs[job_id]["result"] = _serialize_backtest_result(result)
    except Exception as e:
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(e)


def _run_screen_backtest(job_id: str, request: ScreenBacktestRequest):
    try:
        from src.backtest.engine import BacktestEngine
        engine = BacktestEngine()
        result = engine.run_screen_backtest(
            tickers=request.tickers,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
            hold_mode=request.hold_mode,
            hold_period_days=request.hold_period_days,
            exit_criteria=request.exit_criteria,
            benchmark=request.benchmark,
        )
        _jobs[job_id]["status"] = "complete"
        _jobs[job_id]["result"] = _serialize_backtest_result(result)
    except AttributeError:
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = (
            "run_screen_backtest() not yet implemented. Run Phase 3 setup."
        )
    except Exception as e:
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(e)


@router.post("/backtest/strategy")
async def run_strategy_backtest(request: StrategyBacktestRequest, background_tasks: BackgroundTasks):
    """
    Run the existing signal-based strategy backtest for a fund.
    Polls via GET /api/backtest/status/{job_id}.
    """
    job_id = str(uuid4())
    _jobs[job_id] = {"status": "running", "result": None, "error": None}
    background_tasks.add_task(_run_strategy_backtest, job_id, request)
    return {"job_id": job_id, "status": "running", "message": f"Strategy backtest started for {request.fund_name}"}


@router.post("/backtest/screen")
async def run_screen_backtest(request: ScreenBacktestRequest, background_tasks: BackgroundTasks):
    """
    Run a portfolio backtest on a screened stock list.
    Buys all input tickers equally weighted on start_date,
    exits via fixed hold period or criteria-based signals.
    Polls via GET /api/backtest/status/{job_id}.
    """
    if not request.tickers:
        raise HTTPException(status_code=400, detail="tickers list cannot be empty")
    job_id = str(uuid4())
    _jobs[job_id] = {"status": "running", "result": None, "error": None}
    background_tasks.add_task(_run_screen_backtest, job_id, request)
    return {
        "job_id": job_id,
        "status": "running",
        "message": f"Screen backtest started: {len(request.tickers)} tickers, {request.hold_mode} mode",
    }


@router.get("/backtest/status/{job_id}", response_model=BacktestJobStatus)
async def get_backtest_status(job_id: str):
    """Poll backtest job status."""
    job = _jobs.get(job_id)
    if not job:
        return BacktestJobStatus(job_id=job_id, status="not_found")
    return BacktestJobStatus(job_id=job_id, **job)


@router.get("/backtest/results/{fund_name}")
async def get_saved_backtest_results(fund_name: str):
    """Load most recent saved backtest results for a fund."""
    try:
        from src.utils import load_parquet
        summary_df = load_parquet("backtest", f"summary_{fund_name}")
        equity_df = load_parquet("backtest", f"equity_{fund_name}")
        trades_df = load_parquet("backtest", f"trades_{fund_name}")

        return {
            "fund": fund_name,
            "summary": summary_df.to_dict("records") if summary_df is not None else [],
            "equity_curve": equity_df.tail(500).to_dict("records") if equity_df is not None else [],
            "trades": trades_df.tail(200).to_dict("records") if trades_df is not None else [],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
