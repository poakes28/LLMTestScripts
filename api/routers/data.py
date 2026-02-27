"""
Data collection endpoints: trigger price/fundamentals refresh.
"""
from typing import Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

import api.deps  # noqa

router = APIRouter()
_jobs: Dict[str, Dict] = {}


class RefreshRequest(BaseModel):
    tickers: Optional[List[str]] = None
    period: str = "2y"


def _run_price_refresh(job_id: str):
    try:
        from src.collector.price_fetcher import PriceFetcher
        fetcher = PriceFetcher()
        df = fetcher.run_price_pull()
        _jobs[job_id]["status"] = "complete"
        _jobs[job_id]["result"] = {"records_fetched": len(df) if df is not None else 0}
    except Exception as e:
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(e)


def _run_historical_refresh(job_id: str, tickers: Optional[List[str]], period: str):
    try:
        from src.collector.price_fetcher import PriceFetcher
        fetcher = PriceFetcher()
        df = fetcher.fetch_historical_prices(tickers=tickers, period=period)
        if df is not None and not df.empty:
            fetcher.save_prices(df)
        _jobs[job_id]["status"] = "complete"
        _jobs[job_id]["result"] = {"records_fetched": len(df) if df is not None else 0}
    except Exception as e:
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(e)


def _run_fundamentals_refresh(job_id: str, tickers: Optional[List[str]]):
    try:
        from src.collector.price_fetcher import PriceFetcher
        fetcher = PriceFetcher()
        fetcher.run_fundamentals_pull()
        _jobs[job_id]["status"] = "complete"
        _jobs[job_id]["result"] = {"status": "fundamentals updated"}
    except Exception as e:
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(e)


@router.post("/data/refresh/prices")
async def refresh_prices(background_tasks: BackgroundTasks):
    """Trigger current price refresh for all watchlist tickers."""
    job_id = str(uuid4())
    _jobs[job_id] = {"status": "running", "result": None, "error": None}
    background_tasks.add_task(_run_price_refresh, job_id)
    return {"job_id": job_id, "status": "running", "message": "Price refresh started"}


@router.post("/data/refresh/historical")
async def refresh_historical(request: RefreshRequest, background_tasks: BackgroundTasks):
    """Trigger historical price re-pull."""
    job_id = str(uuid4())
    _jobs[job_id] = {"status": "running", "result": None, "error": None}
    background_tasks.add_task(_run_historical_refresh, job_id, request.tickers, request.period)
    return {"job_id": job_id, "status": "running", "message": f"Historical refresh started (period={request.period})"}


@router.post("/data/refresh/fundamentals")
async def refresh_fundamentals(request: RefreshRequest, background_tasks: BackgroundTasks):
    """Trigger fundamentals refresh."""
    job_id = str(uuid4())
    _jobs[job_id] = {"status": "running", "result": None, "error": None}
    background_tasks.add_task(_run_fundamentals_refresh, job_id, request.tickers)
    return {"job_id": job_id, "status": "running", "message": "Fundamentals refresh started"}


@router.get("/data/refresh/status/{job_id}")
async def get_refresh_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        return {"job_id": job_id, "status": "not_found"}
    return {"job_id": job_id, **job}


@router.get("/data/status")
async def get_data_status():
    """Return timestamps and record counts for cached data."""
    try:
        from src.utils import load_parquet, get_data_dir
        import os

        result = {}

        # Price data status
        prices_df = load_parquet("prices", "prices_daily")
        if prices_df is not None and not prices_df.empty:
            result["prices_records"] = len(prices_df)
            result["prices_tickers"] = prices_df["ticker"].nunique() if "ticker" in prices_df.columns else 0
            result["prices_last_date"] = str(prices_df["date"].max()) if "date" in prices_df.columns else None
        else:
            result["prices_records"] = 0
            result["prices_tickers"] = 0
            result["prices_last_date"] = None

        # Fundamentals status
        fund_df = load_parquet("analysis", "fundamentals")
        if fund_df is not None and not fund_df.empty:
            result["fundamentals_records"] = len(fund_df)
            result["fundamentals_last_date"] = str(fund_df["date"].max()) if "date" in fund_df.columns else None
        else:
            result["fundamentals_records"] = 0
            result["fundamentals_last_date"] = None

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
