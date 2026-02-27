"""Pydantic models for the stock screener endpoints."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class ScreenerCriteria(BaseModel):
    # Fundamental filters
    pe_ratio_max: Optional[float] = 30.0
    roe_min: Optional[float] = 0.10
    debt_to_equity_max: Optional[float] = 2.0
    current_ratio_min: Optional[float] = 1.0
    revenue_growth_min: Optional[float] = 0.03
    profit_margin_min: Optional[float] = 0.05
    roa_min: Optional[float] = 0.03
    earnings_growth_min: Optional[float] = 0.0
    peg_ratio_max: Optional[float] = None
    market_cap_min: Optional[float] = 500_000_000
    market_cap_max: Optional[float] = None
    sectors_include: List[str] = []
    sectors_exclude: List[str] = []
    # Technical filters (applied in phase 2 only)
    require_above_sma200: bool = False
    require_bullish_macd: bool = False
    rsi_max: Optional[float] = None
    rsi_min: Optional[float] = None
    min_adx: Optional[float] = None


class ScreenRequest(BaseModel):
    criteria: ScreenerCriteria
    include_technical: bool = True
    universe_override: Optional[List[str]] = None  # custom ticker list instead of Russell 3000


class ScreenResultItem(BaseModel):
    ticker: str
    name: str
    sector: str
    fundamental_score: float
    technical_signal: Optional[str] = None
    technical_confidence: Optional[float] = None
    composite_score: float
    metrics: Dict[str, Any] = {}


class ScreenProgress(BaseModel):
    phase: str
    count: int
    total: int
    message: str


class ScreenResponse(BaseModel):
    results: List[ScreenResultItem]
    phase1_count: int
    phase2_count: int
    total_screened: int
    duration_seconds: float
    timestamp: str
    criteria_used: Dict[str, Any]


class UniverseStatus(BaseModel):
    ticker_count: int
    last_updated: Optional[str] = None
    source: str
    cache_age_days: Optional[float] = None
    is_stale: bool


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # "running" | "complete" | "failed" | "not_found"
    progress: Optional[ScreenProgress] = None
    result: Optional[ScreenResponse] = None
    error: Optional[str] = None
