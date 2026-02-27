import axios from 'axios';
import type {
  ScreenerCriteria, JobStatus, UniverseStatus, FundamentalsCacheStatus,
  Recommendation,
  PortfolioSummary, LLMAnalyzeResponse, TechnicalConfig,
} from '../types';

const api = axios.create({
  baseURL: '/api',
  timeout: 300_000, // 5 min for long-running screener
});

// ── Screener ────────────────────────────────────────────────────────────────

export const startScreen = (criteria: ScreenerCriteria, include_technical: boolean, tickers?: string[]) =>
  api.post<{ job_id: string; status: string }>('/screen', { criteria, include_technical, tickers });

export const getScreenStatus = (jobId: string) =>
  api.get<JobStatus>(`/screen/status/${jobId}`);

export const getUniverseStatus = () =>
  api.get<UniverseStatus>('/universe/status');

export const updateUniverse = () =>
  api.post('/universe/update');

export const getCacheStatus = () =>
  api.get<FundamentalsCacheStatus>('/screen/cache/status');

export const warmCache = () =>
  api.post<{ job_id: string; status: string; message: string }>('/screen/cache/warm');

// ── LLM ─────────────────────────────────────────────────────────────────────

export const analyzeLLM = (stocks: object[], criteria?: ScreenerCriteria, user_notes?: string) =>
  api.post<LLMAnalyzeResponse>('/llm/analyze', { stocks, criteria, user_notes });

export const getLLMStatus = () =>
  api.get('/llm/status');

// ── Backtest ─────────────────────────────────────────────────────────────────

export const startScreenBacktest = (params: {
  tickers: string[];
  start_date: string;
  end_date: string;
  initial_capital: number;
  hold_mode: string;
  hold_period_days: number;
  benchmark?: string;
}) => api.post<{ job_id: string; status: string }>('/backtest/screen', params);

export const getBacktestStatus = (jobId: string) =>
  api.get<JobStatus>(`/backtest/status/${jobId}`);

// ── Analysis ─────────────────────────────────────────────────────────────────

export const getFundBuys = (fund: string, n = 10) =>
  api.get<Recommendation[]>(`/analysis/${fund}/buys`, { params: { n } });

export const getFundSells = (fund: string, n = 10) =>
  api.get<Recommendation[]>(`/analysis/${fund}/sells`, { params: { n } });

export const runAnalysis = (fund?: string) =>
  api.post<{ job_id: string }>('/analysis/run', { fund_name: fund });

export const getAnalysisStatus = (jobId: string) =>
  api.get<JobStatus>(`/analysis/status/${jobId}`);

export const getTicker = (symbol: string) =>
  api.get(`/ticker/${symbol}`);

// ── Portfolio ─────────────────────────────────────────────────────────────────

export const getAllPortfolios = () =>
  api.get<Record<string, PortfolioSummary>>('/portfolio/all');

export const getPortfolio = (fund: string) =>
  api.get<PortfolioSummary>(`/portfolio/${fund}`);

// ── Config ────────────────────────────────────────────────────────────────────

export const getConfig = (section: string) =>
  api.get<TechnicalConfig>(`/config/${section}`);

export const putConfig = (section: string, data: object) =>
  api.put(`/config/${section}`, data);

export const getWatchlist = () =>
  api.get('/config/watchlist');

// ── Data ──────────────────────────────────────────────────────────────────────

export const refreshPrices = () => api.post('/data/refresh/prices');
export const refreshHistorical = () => api.post('/data/refresh/historical');
export const refreshFundamentals = () => api.post('/data/refresh/fundamentals');
export const getDataStatus = () => api.get('/data/status');

// ── Report ────────────────────────────────────────────────────────────────────

export const generateReport = () => api.post('/report/generate');
export const getLatestReport = () => api.get('/report/latest');
export const listReports = () => api.get('/report/list');

// ── Health ────────────────────────────────────────────────────────────────────

export const getHealth = () => api.get('/health');
