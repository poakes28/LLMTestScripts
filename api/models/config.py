"""Pydantic models for configuration endpoints."""
from typing import Any, Dict, Optional
from pydantic import BaseModel


class TechnicalConfig(BaseModel):
    rsi_period: Optional[int] = None
    rsi_oversold: Optional[int] = None
    rsi_overbought: Optional[int] = None
    macd_fast: Optional[int] = None
    macd_slow: Optional[int] = None
    macd_signal: Optional[int] = None
    sma_short: Optional[int] = None
    sma_long: Optional[int] = None
    sma_trend: Optional[int] = None
    ema_short: Optional[int] = None
    ema_long: Optional[int] = None
    volume_avg_period: Optional[int] = None
    atr_period: Optional[int] = None
    bollinger_period: Optional[int] = None
    bollinger_std: Optional[float] = None
    support_resistance_window: Optional[int] = None
    support_resistance_touches: Optional[int] = None


class FundamentalConfig(BaseModel):
    pe_ratio_max: Optional[float] = None
    peg_ratio_max: Optional[float] = None
    roe_min: Optional[float] = None
    roa_min: Optional[float] = None
    debt_to_equity_max: Optional[float] = None
    current_ratio_min: Optional[float] = None
    quick_ratio_min: Optional[float] = None
    revenue_growth_min: Optional[float] = None
    earnings_growth_min: Optional[float] = None
    profit_margin_min: Optional[float] = None
    free_cash_flow_yield_min: Optional[float] = None
    dividend_yield_min: Optional[float] = None


class RiskParams(BaseModel):
    stop_loss_pct: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    max_position_pct: Optional[float] = None
    max_sector_pct: Optional[float] = None
    max_risk_per_trade: Optional[float] = None
    use_kelly_criterion: Optional[bool] = None
    kelly_fraction: Optional[float] = None


class FundWeights(BaseModel):
    fundamental: Optional[float] = None
    technical: Optional[float] = None


class FundConfig(BaseModel):
    weights: Optional[FundWeights] = None
    risk_params: Optional[RiskParams] = None
    starting_capital: Optional[float] = None


class BacktestConfig(BaseModel):
    default_start_date: Optional[str] = None
    default_end_date: Optional[str] = None
    slippage_pct: Optional[float] = None
    commission_per_trade: Optional[float] = None
    commission_pct: Optional[float] = None
    benchmark: Optional[str] = None
    risk_free_rate: Optional[float] = None
    initial_capital: Optional[float] = None
    min_trade_interval_days: Optional[int] = None


class LLMConfig(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    local_base_url: Optional[str] = None
    local_model: Optional[str] = None
    max_stocks_per_request: Optional[int] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None


class ConfigUpdateResponse(BaseModel):
    status: str
    section: str
    config: Dict[str, Any]
