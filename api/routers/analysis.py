"""
Analysis endpoints: strategy signals, fund recommendations, single ticker lookup.
"""
import asyncio
from typing import Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

import api.deps  # noqa — ensures sys.path is set before src.* imports
from api.models.analysis import (
    AnalysisJobStatus, AnalysisRunRequest, FundAnalysis, Recommendation, TickerAnalysis,
    TechnicalSignal, FundamentalScore, PriceInfo,
)

router = APIRouter()

_jobs: Dict[str, Dict] = {}


# ---------------------------------------------------------------------------
# Background job runner
# ---------------------------------------------------------------------------
def _run_analysis_job(job_id: str, fund: Optional[str], tickers: Optional[list]):
    try:
        from src.analysis.strategies import StrategyEngine
        engine = StrategyEngine()
        results = engine.run_analysis(tickers=tickers)

        if fund:
            results = {fund: results[fund]} if fund in results else {}

        _jobs[job_id]["status"] = "complete"
        _jobs[job_id]["result"] = results
    except Exception as e:
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(e)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/analysis/run")
async def run_analysis(request: AnalysisRunRequest, background_tasks: BackgroundTasks):
    """Trigger a fresh analysis run across all (or specific) funds."""
    job_id = str(uuid4())
    _jobs[job_id] = {"status": "running", "result": None, "error": None}
    background_tasks.add_task(_run_analysis_job, job_id, request.fund, request.tickers)
    return {"job_id": job_id, "status": "running"}


@router.get("/analysis/status/{job_id}", response_model=AnalysisJobStatus)
async def get_analysis_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        return AnalysisJobStatus(job_id=job_id, status="not_found")
    return AnalysisJobStatus(job_id=job_id, **job)


@router.get("/analysis/{fund_name}/buys")
async def get_top_buys(fund_name: str, n: int = Query(default=10, ge=1, le=50)):
    """Return top N buy recommendations for a fund (from last saved analysis)."""
    try:
        from src.analysis.strategies import StrategyEngine
        engine = StrategyEngine()
        buys = engine.get_top_buys(fund_name, n=n)
        return {"fund": fund_name, "buys": buys, "count": len(buys)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analysis/{fund_name}/sells")
async def get_top_sells(fund_name: str, n: int = Query(default=10, ge=1, le=50)):
    """Return top N sell recommendations for a fund."""
    try:
        from src.analysis.strategies import StrategyEngine
        engine = StrategyEngine()
        sells = engine.get_top_sells(fund_name, n=n)
        return {"fund": fund_name, "sells": sells, "count": len(sells)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ticker/{symbol}", response_model=TickerAnalysis)
async def get_ticker_analysis(symbol: str):
    """Full technical + fundamental analysis for a single ticker."""
    symbol = symbol.upper()
    try:
        from src.analysis.technical import TechnicalAnalyzer
        from src.analysis.fundamental import FundamentalAnalyzer
        from src.collector.price_fetcher import PriceFetcher

        fetcher = PriceFetcher()
        price_data = fetcher.load_price_history()
        fundamentals_data = fetcher.load_fundamentals()

        tech_signal = None
        fund_score = None
        price_info = None

        # Technical analysis
        if price_data is not None:
            ticker_df = price_data[price_data["ticker"] == symbol].copy()
            if len(ticker_df) >= 20:
                analyzer = TechnicalAnalyzer()
                ticker_df = analyzer.calculate_indicators(ticker_df)
                sig = analyzer.generate_signals(ticker_df)
                sr = analyzer.find_support_resistance(ticker_df)

                tech_signal = TechnicalSignal(
                    signal=sig.get("signal", "HOLD"),
                    confidence=sig.get("confidence", 0.0),
                    score=sig.get("score", 0.0),
                    reasons=sig.get("reasons", []),
                    entry_price=sig.get("entry_price", 0.0),
                    stop_loss=sig.get("stop_loss", 0.0),
                    target_price=sig.get("target_price", 0.0),
                    risk_reward_ratio=sig.get("risk_reward_ratio", 0.0),
                    support_levels=sr.get("support", []),
                    resistance_levels=sr.get("resistance", []),
                    indicators=sig.get("indicators", {}),
                )

                last_row = ticker_df.iloc[-1]
                price_info = PriceInfo(
                    close=float(last_row.get("close", 0)),
                    date=str(last_row.get("date", "")),
                    return_1d=float(last_row.get("return_1d", 0)) if "return_1d" in last_row else None,
                    return_5d=float(last_row.get("return_5d", 0)) if "return_5d" in last_row else None,
                    return_20d=float(last_row.get("return_20d", 0)) if "return_20d" in last_row else None,
                )

        # Fundamental analysis
        if fundamentals_data is not None:
            ticker_fund = fundamentals_data[fundamentals_data["ticker"] == symbol]
            if not ticker_fund.empty:
                f_data = ticker_fund.iloc[-1].to_dict()
                scorer = FundamentalAnalyzer()
                result = scorer.score_stock(f_data)
                fund_score = FundamentalScore(
                    signal=result.get("signal", "HOLD"),
                    confidence=result.get("confidence", 0.0),
                    total_score=result.get("total_score", 0.0),
                    max_score=result.get("max_score", 100.0),
                    normalized_score=result.get("normalized_score", 0.0),
                    scores=result.get("scores", {}),
                    reasons=result.get("reasons", []),
                    metrics=result.get("metrics", {}),
                )

        if tech_signal is None and fund_score is None:
            return TickerAnalysis(
                ticker=symbol,
                error=f"No data found for {symbol}. Run data collector first.",
            )

        return TickerAnalysis(
            ticker=symbol,
            technical=tech_signal,
            fundamental=fund_score,
            price=price_info,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
