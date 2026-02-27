// TypeScript interfaces matching the FastAPI Pydantic models

export interface ScreenerCriteria {
  pe_ratio_max?: number | null;
  peg_ratio_max?: number | null;
  roe_min?: number | null;
  roa_min?: number | null;
  debt_to_equity_max?: number | null;
  current_ratio_min?: number | null;
  revenue_growth_min?: number | null;
  profit_margin_min?: number | null;
  earnings_growth_min?: number | null;
  market_cap_min?: number | null;
  market_cap_max?: number | null;
  sectors_include?: string[];
  sectors_exclude?: string[];
  require_above_sma200?: boolean;
  require_bullish_macd?: boolean;
  rsi_min?: number | null;
  rsi_max?: number | null;
  min_adx?: number | null;
}

export interface ScreenResultItem {
  ticker: string;
  name: string;
  sector: string;
  fundamental_score: number;
  fundamental_confidence: number;
  fundamental_signal: string;
  technical_signal: string | null;
  technical_confidence: number;
  composite_score: number;
  metrics: Record<string, number | null>;
  reasons: string[];
}

export interface ScreenResponse {
  results: ScreenResultItem[];
  phase1_count: number;
  phase2_count: number;
  total_screened: number;
  duration_seconds: number;
  timestamp: string;
  criteria_used: ScreenerCriteria;
}

export interface JobStatus {
  job_id: string;
  status: 'running' | 'complete' | 'failed' | 'not_found';
  progress?: Record<string, unknown>;
  result?: unknown;
  error?: string | null;
}

export interface UniverseStatus {
  ticker_count: number;
  last_updated: string | null;
  source: string;
  cache_age_days: number | null;
  is_stale: boolean;
}

export interface FundamentalsCacheStatus {
  exists: boolean;
  tickers_cached: number;
  age_hours: number | null;
  cache_date: string | null;
}

// Backtest
export interface EquityCurvePoint {
  date: string;
  total_value: number;
  cash: number;
  invested: number;
}

export interface IndividualReturn {
  ticker: string;
  entry_date: string;
  exit_date: string;
  entry_price: number;
  exit_price: number;
  return_pct: number;
  hold_days: number;
  exit_reason: string;
}

export interface BacktestMetrics {
  total_return: number;
  annual_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  annual_volatility: number;
  win_rate?: number;
  total_trades?: number;
  [key: string]: number | undefined;
}

export interface ScreenBacktestResponse {
  tickers: string[];
  active_tickers: string[];
  start_date: string;
  end_date: string;
  initial_capital: number;
  final_value: number;
  hold_mode: string;
  equity_curve: EquityCurvePoint[];
  individual_returns: IndividualReturn[];
  metrics: BacktestMetrics;
  benchmark: string;
  benchmark_metrics: BacktestMetrics;
  survivorship_bias_note: string;
  warnings: string[];
}

// Analysis
export interface Recommendation {
  ticker: string;
  signal: string;
  confidence: number;
  composite_score: number;
  fundamental_score?: number;
  technical_signal?: string;
  reasons: string[];
}

export interface FundAnalysis {
  fund: string;
  buys: Recommendation[];
  sells: Recommendation[];
  generated_at: string;
}

// Portfolio
export interface Position {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price?: number;
  market_value?: number;
  unrealized_pnl?: number;
  unrealized_pnl_pct?: number;
}

export interface PortfolioSummary {
  fund: string;
  total_value: number;
  cash: number;
  invested_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  num_positions: number;
  positions: Position[];
}

// LLM
export interface StockCommentary {
  ticker: string;
  rating: 'Strong Buy' | 'Buy' | 'Hold' | 'Avoid';
  summary: string;
  key_positives: string[];
  key_risks: string[];
  confidence: 'High' | 'Medium' | 'Low';
}

export interface CriteriaSuggestion {
  criterion: string;
  current_value: number | null;
  suggested_value: number;
  rationale: string;
}

export interface LLMAnalyzeResponse {
  stock_commentaries: StockCommentary[];
  criteria_suggestions: CriteriaSuggestion[];
  overall_summary: string;
  model_used: string;
  provider_used: string;
  tokens_used: number | null;
}

// Config
export interface TechnicalConfig {
  [key: string]: number | boolean | string;
}
