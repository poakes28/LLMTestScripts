"""Pydantic models for backtesting endpoints."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class ScreenBacktestRequest(BaseModel):
    tickers: List[str]
    start_date: str
    end_date: str
    initial_capital: float = 100_000.0
    hold_mode: str = "fixed"           # "fixed" | "criteria_exit"
    hold_period_days: int = 30         # used when hold_mode="fixed"
    exit_criteria: Optional[Dict[str, Any]] = None  # used when hold_mode="criteria_exit"
    benchmark: str = "SPY"


class StrategyBacktestRequest(BaseModel):
    fund_name: str                     # "fundamental" | "technical" | "balanced"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: Optional[float] = None
    tickers: Optional[List[str]] = None


class EquityCurvePoint(BaseModel):
    date: str
    total_value: float
    cash: float
    invested: float


class IndividualReturn(BaseModel):
    ticker: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    return_pct: float
    hold_days: int
    exit_reason: str


class BacktestMetrics(BaseModel):
    total_return: Optional[float] = None
    annual_return: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    calmar_ratio: Optional[float] = None
    win_rate: Optional[float] = None
    profit_factor: Optional[float] = None
    total_trades: Optional[int] = None
    alpha: Optional[float] = None
    beta: Optional[float] = None
    var_95: Optional[float] = None


class ScreenBacktestResponse(BaseModel):
    tickers: List[str]
    start_date: str
    end_date: str
    initial_capital: float
    final_value: float
    hold_mode: str
    hold_period_days: Optional[int] = None
    equity_curve: List[EquityCurvePoint]
    individual_returns: List[IndividualReturn]
    metrics: BacktestMetrics
    benchmark_metrics: BacktestMetrics
    survivorship_bias_note: str
    warnings: List[str]


class BacktestJobStatus(BaseModel):
    job_id: str
    status: str  # "running" | "complete" | "failed" | "not_found"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
