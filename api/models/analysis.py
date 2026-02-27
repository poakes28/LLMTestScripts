"""Pydantic models for analysis endpoints."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class Recommendation(BaseModel):
    ticker: str
    signal: str
    composite_score: float
    confidence: float
    technical_signal: Optional[str] = None
    fundamental_signal: Optional[str] = None
    entry_price: float = 0.0
    stop_loss: float = 0.0
    target_price: float = 0.0
    risk_reward_ratio: float = 0.0
    sector: str = ""
    reasons: List[str] = []
    fund: str = ""
    date: str = ""


class FundAnalysis(BaseModel):
    fund_name: str
    recommendations: List[Recommendation]
    timestamp: str
    num_tickers_analyzed: int


class AnalysisRunRequest(BaseModel):
    fund: Optional[str] = None       # None = run all funds
    tickers: Optional[List[str]] = None


class AnalysisJobStatus(BaseModel):
    job_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TechnicalSignal(BaseModel):
    signal: str
    confidence: float
    score: float
    reasons: List[str] = []
    entry_price: float = 0.0
    stop_loss: float = 0.0
    target_price: float = 0.0
    risk_reward_ratio: float = 0.0
    support_levels: List[float] = []
    resistance_levels: List[float] = []
    indicators: Dict[str, Any] = {}


class FundamentalScore(BaseModel):
    signal: str
    confidence: float
    total_score: float
    max_score: float
    normalized_score: float
    scores: Dict[str, float] = {}
    reasons: List[str] = []
    metrics: Dict[str, Any] = {}


class PriceInfo(BaseModel):
    close: float
    date: str
    return_1d: Optional[float] = None
    return_5d: Optional[float] = None
    return_20d: Optional[float] = None


class TickerAnalysis(BaseModel):
    ticker: str
    technical: Optional[TechnicalSignal] = None
    fundamental: Optional[FundamentalScore] = None
    price: Optional[PriceInfo] = None
    error: Optional[str] = None
