"""
Stock screener endpoints.
Full implementation in Phase 2 (src/screener/ module).
Placeholder routes return 501 until screener module is built.
"""
import time
from typing import Dict
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException

import api.deps  # noqa
from api.models.screener import (
    JobStatusResponse, ScreenProgress, ScreenRequest, ScreenResponse, UniverseStatus,
)

router = APIRouter()

# In-memory job store (single worker only)
_jobs: Dict[str, Dict] = {}


def _run_screen_job(job_id: str, request: ScreenRequest):
    try:
        from src.screener.screener import StockScreener
        screener = StockScreener()
        result = screener.run_screen(
            criteria=request.criteria.model_dump(),
            include_technical=request.include_technical,
            tickers=request.universe_override,
        )
        _jobs[job_id]["status"] = "complete"
        _jobs[job_id]["result"] = result
    except ImportError:
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = "Screener module not yet installed. Run Phase 2 setup."
    except Exception as e:
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(e)


@router.post("/screen")
async def start_screen(request: ScreenRequest, background_tasks: BackgroundTasks):
    """
    Start a Russell 3000 screen with the given criteria.
    Returns a job_id to poll for results via GET /api/screen/status/{job_id}.
    Full 3000-stock screens take 5-20 minutes.
    """
    job_id = str(uuid4())
    _jobs[job_id] = {"status": "running", "progress": None, "result": None, "error": None}
    background_tasks.add_task(_run_screen_job, job_id, request)
    return {"job_id": job_id, "status": "running", "message": "Screen started"}


@router.get("/screen/status/{job_id}")
async def get_screen_status(job_id: str):
    """Poll screen job status."""
    job = _jobs.get(job_id)
    if not job:
        return {"job_id": job_id, "status": "not_found"}
    return {"job_id": job_id, **job}


@router.get("/universe/status")
async def get_universe_status():
    """Return Russell 3000 universe cache status."""
    try:
        from src.screener.universe import UniverseManager
        mgr = UniverseManager()
        status = mgr.get_status()
        return status
    except ImportError:
        return {
            "ticker_count": 0,
            "last_updated": None,
            "source": "not_installed",
            "cache_age_days": None,
            "is_stale": True,
            "message": "Screener module not yet installed. Run Phase 2 setup.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/screen/cache/status")
async def get_cache_status():
    """Return fundamentals cache age and ticker count."""
    try:
        from src.screener.screener import StockScreener
        screener = StockScreener()
        path = screener._cache_path()
        if not path.exists():
            return {"exists": False, "tickers_cached": 0, "age_hours": None, "cache_date": None}
        age_hours = round((time.time() - path.stat().st_mtime) / 3600, 1)
        import pandas as pd
        df = pd.read_parquet(path)
        return {
            "exists": True,
            "tickers_cached": len(df),
            "age_hours": age_hours,
            "cache_date": path.stem.replace("fundamentals_cache_", ""),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _run_warm_cache_job(job_id: str):
    try:
        from src.screener.screener import StockScreener
        screener = StockScreener()
        result = screener.warm_cache()
        _jobs[job_id]["status"] = "complete"
        _jobs[job_id]["result"] = result
    except Exception as e:
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(e)


@router.post("/screen/cache/warm")
async def warm_cache(background_tasks: BackgroundTasks):
    """Pre-warm fundamentals cache in background (runs full ~3000-ticker fetch, 6–10 min)."""
    job_id = str(uuid4())
    _jobs[job_id] = {"status": "running", "progress": None, "result": None, "error": None}
    background_tasks.add_task(_run_warm_cache_job, job_id)
    return {"job_id": job_id, "status": "running", "message": "Cache warming started (6–10 min)"}


@router.post("/universe/update")
async def update_universe(background_tasks: BackgroundTasks):
    """Force re-download of the Russell 3000 universe list."""
    try:
        from src.screener.universe import UniverseManager

        def _do_update():
            mgr = UniverseManager()
            mgr.get_universe(force_refresh=True)

        background_tasks.add_task(_do_update)
        return {"status": "started", "message": "Universe update started in background"}
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="Screener module not yet installed. Run Phase 2 setup."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
