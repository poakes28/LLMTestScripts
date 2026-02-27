import { useState, useCallback, useEffect } from 'react';
import { startScreen, getScreenStatus, analyzeLLM, getCacheStatus, warmCache } from '../api/client';
import type { ScreenerCriteria, ScreenResultItem, LLMAnalyzeResponse, FundamentalsCacheStatus } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorBanner from '../components/ErrorBanner';


const defaultCriteria: ScreenerCriteria = {
  pe_ratio_max: 40,
  roe_min: 0.10,
  debt_to_equity_max: 3.0,
  current_ratio_min: 1.0,
  revenue_growth_min: 0.0,
  profit_margin_min: 0.05,
  market_cap_min: 500_000_000,
  require_above_sma200: false,
  require_bullish_macd: false,
  sectors_include: [],
  sectors_exclude: [],
};

function fmt(v: number | null | undefined, pct = false): string {
  if (v == null) return '—';
  return pct ? `${(v * 100).toFixed(1)}%` : v.toFixed(2);
}

const signalColor = (s: string | null) => {
  if (!s) return '#64748b';
  if (s === 'BUY' || s === 'Strong Buy' || s === 'Buy') return '#00d4aa';
  if (s === 'SELL' || s === 'Avoid') return '#f87171';
  return '#fbbf24';
};

export default function Screener() {
  const [criteria, setCriteria] = useState<ScreenerCriteria>(defaultCriteria);
  const [includeTechnical, setIncludeTechnical] = useState(true);
  const [tickerOverride, setTickerOverride] = useState('');
  const [userNotes, setUserNotes] = useState('');

  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<ScreenResultItem[]>([]);
  const [meta, setMeta] = useState<Record<string, unknown> | null>(null);

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [llmLoading, setLlmLoading] = useState(false);
  const [llmResult, setLlmResult] = useState<LLMAnalyzeResponse | null>(null);
  const [llmError, setLlmError] = useState<string | null>(null);

  const [sortKey, setSortKey] = useState<keyof ScreenResultItem>('composite_score');
  const [sortAsc, setSortAsc] = useState(false);

  const [cacheStatus, setCacheStatus] = useState<FundamentalsCacheStatus | null>(null);
  const [warmingCache, setWarmingCache] = useState(false);

  useEffect(() => {
    getCacheStatus().then(r => setCacheStatus(r.data)).catch(() => {});
  }, []);

  const handleWarmCache = async () => {
    setWarmingCache(true);
    try {
      await warmCache();
      // Poll until the warm job finishes (status endpoint reflects file presence)
      for (let i = 0; i < 120; i++) {
        await new Promise(r => setTimeout(r, 5000));
        const res = await getCacheStatus();
        setCacheStatus(res.data);
        if (res.data.exists) break;
      }
    } catch {
      // ignore — badge will stay stale
    }
    setWarmingCache(false);
  };

  const poll = useCallback(async (jobId: string) => {
    for (let i = 0; i < 300; i++) {
      await new Promise(r => setTimeout(r, 3000));
      const res = await getScreenStatus(jobId);
      const { status, progress: prog, result, error: err } = res.data as {
        status: string;
        progress?: { phase?: string; count?: number; total?: number };
        result?: unknown;
        error?: string;
      };
      if (prog) {
        setProgress(`${prog.phase || ''} — ${prog.count ?? 0}/${prog.total ?? 0}`);
      }
      if (status === 'complete') {
        const r = result as { results: ScreenResultItem[]; phase1_count: number; phase2_count: number; total_screened: number; duration_seconds: number };
        setResults(r.results || []);
        setMeta(r as Record<string, unknown>);
        setLoading(false);
        setProgress('');
        getCacheStatus().then(res => setCacheStatus(res.data)).catch(() => {});
        return;
      }
      if (status === 'failed') {
        setError(err || 'Screen job failed');
        setLoading(false);
        return;
      }
    }
    setError('Screen timed out after 15 minutes');
    setLoading(false);
  }, []);

  const runScreen = async () => {
    setError(null);
    setLoading(true);
    setResults([]);
    setLlmResult(null);
    setSelected(new Set());
    setProgress('Starting...');
    try {
      const tickers = tickerOverride
        ? tickerOverride.split(/[\s,\n]+/).map(t => t.trim().toUpperCase()).filter(Boolean)
        : undefined;
      const res = await startScreen(criteria, includeTechnical, tickers);
      await poll(res.data.job_id);
    } catch (e: unknown) {
      setError((e as { message?: string }).message || 'Network error');
      setLoading(false);
    }
  };

  const runLLM = async () => {
    const stocks = results.filter(r => selected.has(r.ticker));
    if (!stocks.length) return;
    setLlmLoading(true);
    setLlmError(null);
    try {
      const res = await analyzeLLM(stocks, criteria, userNotes);
      setLlmResult(res.data);
    } catch (e: unknown) {
      setLlmError((e as { message?: string }).message || 'LLM error');
    }
    setLlmLoading(false);
  };

  const sorted = [...results].sort((a, b) => {
    const av = a[sortKey] as number | string | null;
    const bv = b[sortKey] as number | string | null;
    if (av == null) return 1;
    if (bv == null) return -1;
    return sortAsc ? (av < bv ? -1 : 1) : (av > bv ? -1 : 1);
  });

  const thClick = (key: keyof ScreenResultItem) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(false); }
  };

  const numCriteria = (key: keyof ScreenerCriteria, label: string, step = 0.1) => (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: '0.8rem', color: '#94a3b8' }}>
      {label}
      <input
        type="number" step={step}
        value={(criteria[key] as number | undefined) ?? ''}
        onChange={e => setCriteria(c => ({ ...c, [key]: e.target.value === '' ? null : parseFloat(e.target.value) }))}
        style={{ background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', borderRadius: 6, padding: '0.4rem', width: '100%' }}
      />
    </label>
  );

  return (
    <div style={{ padding: '1rem', maxWidth: 1200, margin: '0 auto' }}>
      <h1 style={{ color: '#e2e8f0', fontSize: '1.4rem', marginBottom: '1rem' }}>Stock Screener</h1>

      {/* Criteria Panel */}
      <details open style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: '1rem', marginBottom: '1rem' }}>
        <summary style={{ color: '#94a3b8', cursor: 'pointer', fontWeight: 600, marginBottom: '1rem' }}>
          Screening Criteria
        </summary>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: '0.75rem' }}>
          {numCriteria('pe_ratio_max', 'P/E Max')}
          {numCriteria('roe_min', 'ROE Min', 0.01)}
          {numCriteria('roa_min', 'ROA Min', 0.01)}
          {numCriteria('debt_to_equity_max', 'D/E Max')}
          {numCriteria('current_ratio_min', 'Curr Ratio Min')}
          {numCriteria('revenue_growth_min', 'Rev Growth Min', 0.01)}
          {numCriteria('profit_margin_min', 'Profit Margin Min', 0.01)}
          {numCriteria('earnings_growth_min', 'Earnings Growth Min', 0.01)}
          {numCriteria('market_cap_min', 'Mkt Cap Min (M)', 100_000_000)}
          {numCriteria('rsi_min', 'RSI Min')}
          {numCriteria('rsi_max', 'RSI Max')}
          {numCriteria('min_adx', 'ADX Min')}
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', marginTop: '1rem' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#94a3b8', fontSize: '0.85rem', cursor: 'pointer' }}>
            <input type="checkbox" checked={criteria.require_above_sma200 ?? false}
              onChange={e => setCriteria(c => ({ ...c, require_above_sma200: e.target.checked }))} />
            Above 200-day SMA
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#94a3b8', fontSize: '0.85rem', cursor: 'pointer' }}>
            <input type="checkbox" checked={criteria.require_bullish_macd ?? false}
              onChange={e => setCriteria(c => ({ ...c, require_bullish_macd: e.target.checked }))} />
            Bullish MACD
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#94a3b8', fontSize: '0.85rem', cursor: 'pointer' }}>
            <input type="checkbox" checked={includeTechnical}
              onChange={e => setIncludeTechnical(e.target.checked)} />
            Include Technical Phase
          </label>
        </div>

        <div style={{ marginTop: '1rem', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: '0.8rem', color: '#94a3b8' }}>
            Ticker Override (blank = Russell 3000)
            <textarea rows={2} value={tickerOverride}
              onChange={e => setTickerOverride(e.target.value)}
              placeholder="AAPL MSFT GOOGL..."
              style={{ background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', borderRadius: 6, padding: '0.4rem', resize: 'vertical' }} />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: '0.8rem', color: '#94a3b8' }}>
            Sectors to Exclude (comma-separated)
            <input value={(criteria.sectors_exclude ?? []).join(', ')}
              onChange={e => setCriteria(c => ({
                ...c,
                sectors_exclude: e.target.value.split(',').map(s => s.trim()).filter(Boolean),
              }))}
              placeholder="Energy, Utilities"
              style={{ background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', borderRadius: 6, padding: '0.4rem' }} />
          </label>
        </div>
      </details>

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
        <button onClick={runScreen} disabled={loading}
          style={{
            background: loading ? '#1e293b' : '#0891b2', color: '#fff',
            border: 'none', borderRadius: 8, padding: '0.6rem 1.5rem',
            fontSize: '0.95rem', cursor: loading ? 'not-allowed' : 'pointer',
          }}>
          {loading ? `Running… ${progress}` : 'Run Screener'}
        </button>

        {/* Cache status badge */}
        {cacheStatus !== null && (
          <span style={{
            fontSize: '0.78rem', padding: '0.25rem 0.6rem', borderRadius: 6,
            background: cacheStatus.exists && (cacheStatus.age_hours ?? 99) < 24 ? '#064e3b' : '#1e293b',
            color: cacheStatus.exists && (cacheStatus.age_hours ?? 99) < 24 ? '#00d4aa' : '#64748b',
            border: '1px solid',
            borderColor: cacheStatus.exists && (cacheStatus.age_hours ?? 99) < 24 ? '#00d4aa' : '#334155',
          }}>
            {cacheStatus.exists
              ? `Cache: fresh (${cacheStatus.age_hours}h old, ${cacheStatus.tickers_cached} tickers) — next screen ~5s`
              : 'Cache: none — first screen ~8 min'}
          </span>
        )}

        {/* Warm Cache button */}
        <button
          onClick={handleWarmCache}
          disabled={warmingCache || loading}
          style={{
            background: 'none', border: '1px solid #334155', color: warmingCache ? '#64748b' : '#94a3b8',
            borderRadius: 8, padding: '0.35rem 0.9rem', fontSize: '0.8rem',
            cursor: warmingCache || loading ? 'not-allowed' : 'pointer',
          }}>
          {warmingCache ? 'Warming…' : 'Warm Cache'}
        </button>
      </div>

      {error && <ErrorBanner message={error} />}
      {loading && <LoadingSpinner label={`Screening… ${progress}`} />}

      {/* Results */}
      {results.length > 0 && (
        <>
          <div style={{ color: '#94a3b8', fontSize: '0.85rem', marginBottom: '0.5rem' }}>
            {results.length} results | {(meta?.total_screened as number | undefined) ?? '?'} screened |{' '}
            {(meta?.duration_seconds as number | undefined) ?? '?'}s |{' '}
            <button onClick={() => setSelected(new Set(results.map(r => r.ticker)))}
              style={{ background: 'none', border: 'none', color: '#00d4aa', cursor: 'pointer', fontSize: '0.85rem' }}>
              Select All
            </button>{' '}|{' '}
            <button onClick={() => setSelected(new Set())}
              style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: '0.85rem' }}>
              Clear
            </button>
          </div>

          <div style={{ overflowX: 'auto', marginBottom: '1rem' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
              <thead>
                <tr style={{ background: '#0f172a', color: '#64748b' }}>
                  <th style={{ padding: '0.5rem', textAlign: 'center' }}>✓</th>
                  {([
                    ['ticker', 'Ticker'],
                    ['sector', 'Sector'],
                    ['fundamental_score', 'Fund Score'],
                    ['fundamental_signal', 'Fund Sig'],
                    ['technical_signal', 'Tech Sig'],
                    ['composite_score', 'Composite'],
                  ] as [keyof ScreenResultItem, string][]).map(([k, label]) => (
                    <th key={k} onClick={() => thClick(k)}
                      style={{ padding: '0.5rem', textAlign: 'left', cursor: 'pointer', userSelect: 'none' }}>
                      {label} {sortKey === k ? (sortAsc ? '↑' : '↓') : ''}
                    </th>
                  ))}
                  <th style={{ padding: '0.5rem', textAlign: 'left' }}>P/E</th>
                  <th style={{ padding: '0.5rem', textAlign: 'left' }}>ROE</th>
                  <th style={{ padding: '0.5rem', textAlign: 'left' }}>Margin</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((r, i) => (
                  <tr key={r.ticker} style={{ background: i % 2 === 0 ? '#0f172a' : '#1a2332', cursor: 'pointer' }}
                    onClick={() => setSelected(s => {
                      const next = new Set(s);
                      next.has(r.ticker) ? next.delete(r.ticker) : next.add(r.ticker);
                      return next;
                    })}>
                    <td style={{ padding: '0.4rem 0.5rem', textAlign: 'center' }}>
                      <input type="checkbox" checked={selected.has(r.ticker)} readOnly />
                    </td>
                    <td style={{ padding: '0.4rem 0.5rem', color: '#e2e8f0', fontWeight: 600 }}>{r.ticker}</td>
                    <td style={{ padding: '0.4rem 0.5rem', color: '#94a3b8' }}>{r.sector}</td>
                    <td style={{ padding: '0.4rem 0.5rem', color: '#e2e8f0' }}>{r.fundamental_score.toFixed(1)}</td>
                    <td style={{ padding: '0.4rem 0.5rem', color: signalColor(r.fundamental_signal) }}>{r.fundamental_signal}</td>
                    <td style={{ padding: '0.4rem 0.5rem', color: signalColor(r.technical_signal) }}>{r.technical_signal ?? '—'}</td>
                    <td style={{ padding: '0.4rem 0.5rem', color: '#e2e8f0', fontWeight: 600 }}>{r.composite_score.toFixed(3)}</td>
                    <td style={{ padding: '0.4rem 0.5rem', color: '#94a3b8' }}>{fmt(r.metrics?.pe_ratio)}</td>
                    <td style={{ padding: '0.4rem 0.5rem', color: '#94a3b8' }}>{fmt(r.metrics?.roe, true)}</td>
                    <td style={{ padding: '0.4rem 0.5rem', color: '#94a3b8' }}>{fmt(r.metrics?.profit_margin, true)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginBottom: '1.5rem' }}>
            <button
              onClick={runLLM}
              disabled={selected.size === 0 || llmLoading}
              style={{
                background: selected.size === 0 ? '#1e293b' : '#7c3aed', color: '#fff',
                border: 'none', borderRadius: 8, padding: '0.5rem 1.25rem',
                cursor: selected.size === 0 ? 'not-allowed' : 'pointer', fontSize: '0.875rem',
              }}>
              {llmLoading ? 'Analyzing…' : `Analyze ${selected.size} with LLM`}
            </button>
            <button
              onClick={() => {
                const tickers = [...selected].join('\n');
                localStorage.setItem('backtest_tickers', tickers);
                window.location.href = '/backtest';
              }}
              disabled={selected.size === 0}
              style={{
                background: selected.size === 0 ? '#1e293b' : '#0891b2', color: '#fff',
                border: 'none', borderRadius: 8, padding: '0.5rem 1.25rem',
                cursor: selected.size === 0 ? 'not-allowed' : 'pointer', fontSize: '0.875rem',
              }}>
              Send {selected.size} to Backtest
            </button>
          </div>

          {/* LLM Notes input */}
          <label style={{ display: 'block', marginBottom: '1rem', fontSize: '0.8rem', color: '#94a3b8' }}>
            LLM User Notes (optional)
            <textarea rows={2} value={userNotes} onChange={e => setUserNotes(e.target.value)}
              placeholder="Focus on dividend payers, ignore high-debt tech..."
              style={{ display: 'block', width: '100%', marginTop: 4, background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', borderRadius: 6, padding: '0.4rem', resize: 'vertical', boxSizing: 'border-box' }} />
          </label>
        </>
      )}

      {llmError && <ErrorBanner message={llmError} />}
      {llmLoading && <LoadingSpinner label="LLM analyzing (may take 30–90 seconds)…" />}

      {/* LLM Results */}
      {llmResult && (
        <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: '1rem' }}>
          <h2 style={{ color: '#e2e8f0', fontSize: '1.1rem', marginBottom: '0.75rem' }}>
            LLM Analysis — {llmResult.model_used} ({llmResult.provider_used})
            {llmResult.tokens_used != null && <span style={{ color: '#64748b', fontWeight: 400, fontSize: '0.8rem' }}> · {llmResult.tokens_used.toLocaleString()} tokens</span>}
          </h2>

          {llmResult.overall_summary && (
            <p style={{ color: '#94a3b8', fontSize: '0.9rem', marginBottom: '1rem', lineHeight: 1.5 }}>
              {llmResult.overall_summary}
            </p>
          )}

          {llmResult.stock_commentaries.map(c => (
            <details key={c.ticker} style={{ borderBottom: '1px solid #1e293b', padding: '0.5rem 0' }}>
              <summary style={{ cursor: 'pointer', display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                <span style={{ color: '#e2e8f0', fontWeight: 600, minWidth: 60 }}>{c.ticker}</span>
                <span style={{ color: signalColor(c.rating), fontWeight: 500, fontSize: '0.85rem' }}>{c.rating}</span>
                <span style={{ color: '#64748b', fontSize: '0.8rem' }}>{c.confidence} confidence</span>
              </summary>
              <div style={{ paddingLeft: '1rem', paddingTop: '0.5rem' }}>
                <p style={{ color: '#94a3b8', fontSize: '0.875rem', marginBottom: '0.5rem' }}>{c.summary}</p>
                {c.key_positives.length > 0 && (
                  <ul style={{ color: '#00d4aa', fontSize: '0.8rem', margin: '0.25rem 0', paddingLeft: '1.25rem' }}>
                    {c.key_positives.map((p, i) => <li key={i}>{p}</li>)}
                  </ul>
                )}
                {c.key_risks.length > 0 && (
                  <ul style={{ color: '#f87171', fontSize: '0.8rem', margin: '0.25rem 0', paddingLeft: '1.25rem' }}>
                    {c.key_risks.map((r, i) => <li key={i}>{r}</li>)}
                  </ul>
                )}
              </div>
            </details>
          ))}

          {llmResult.criteria_suggestions.length > 0 && (
            <div style={{ marginTop: '1rem' }}>
              <h3 style={{ color: '#e2e8f0', fontSize: '0.95rem', marginBottom: '0.5rem' }}>Criteria Suggestions</h3>
              {llmResult.criteria_suggestions.map(s => (
                <div key={s.criterion} style={{ background: '#1e293b', borderRadius: 8, padding: '0.5rem 0.75rem', marginBottom: '0.5rem' }}>
                  <span style={{ color: '#00d4aa', fontWeight: 600, fontSize: '0.85rem' }}>{s.criterion}</span>
                  <span style={{ color: '#94a3b8', fontSize: '0.8rem' }}> · {s.current_value ?? 'none'} → {s.suggested_value}</span>
                  <p style={{ color: '#64748b', fontSize: '0.8rem', margin: '0.25rem 0 0' }}>{s.rationale}</p>
                  <button onClick={() => {
                    const k = s.criterion as keyof ScreenerCriteria;
                    setCriteria(c => ({ ...c, [k]: s.suggested_value }));
                  }} style={{ background: '#0f172a', border: '1px solid #334155', color: '#00d4aa', borderRadius: 6, padding: '0.2rem 0.6rem', fontSize: '0.75rem', cursor: 'pointer', marginTop: '0.4rem' }}>
                    Apply
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
