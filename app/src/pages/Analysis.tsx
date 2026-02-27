import { useState, useEffect } from 'react';
import { getFundBuys, getFundSells, getTicker, runAnalysis, getAnalysisStatus } from '../api/client';
import type { Recommendation } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorBanner from '../components/ErrorBanner';

const FUNDS = ['balanced', 'fundamental', 'technical'];
const signalColor = (s: string) => s === 'BUY' ? '#00d4aa' : s === 'SELL' ? '#f87171' : '#fbbf24';

function RecTable({ items, type }: { items: Recommendation[]; type: 'buys' | 'sells' }) {
  if (!items.length) return <p style={{ color: '#64748b', fontSize: '0.85rem' }}>No {type} found.</p>;
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem', marginBottom: '1rem' }}>
      <thead>
        <tr style={{ background: '#0f172a', color: '#64748b' }}>
          {['Ticker', 'Signal', 'Score', 'Confidence', 'Reasons'].map(h => (
            <th key={h} style={{ padding: '0.5rem', textAlign: 'left' }}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {items.map((r, i) => (
          <tr key={r.ticker} style={{ background: i % 2 === 0 ? '#0f172a' : '#1a2332' }}>
            <td style={{ padding: '0.4rem 0.5rem', color: '#e2e8f0', fontWeight: 600 }}>{r.ticker}</td>
            <td style={{ padding: '0.4rem 0.5rem', color: signalColor(r.signal) }}>{r.signal}</td>
            <td style={{ padding: '0.4rem 0.5rem', color: '#94a3b8' }}>{r.composite_score?.toFixed(3) ?? '—'}</td>
            <td style={{ padding: '0.4rem 0.5rem', color: '#94a3b8' }}>{((r.confidence ?? 0) * 100).toFixed(0)}%</td>
            <td style={{ padding: '0.4rem 0.5rem', color: '#64748b', fontSize: '0.75rem' }}>
              {(r.reasons ?? []).slice(0, 2).join('; ')}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function Analysis() {
  const [fund, setFund] = useState('balanced');
  const [buys, setBuys] = useState<Recommendation[]>([]);
  const [sells, setSells] = useState<Recommendation[]>([]);
  const [loadingData, setLoadingData] = useState(false);
  const [dataError, setDataError] = useState<string | null>(null);

  const [symbol, setSymbol] = useState('');
  const [tickerData, setTickerData] = useState<Record<string, unknown> | null>(null);
  const [tickerLoading, setTickerLoading] = useState(false);
  const [tickerError, setTickerError] = useState<string | null>(null);

  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const loadFund = async (f: string) => {
    setLoadingData(true);
    setDataError(null);
    try {
      const [b, s] = await Promise.all([getFundBuys(f, 15), getFundSells(f, 15)]);
      setBuys(b.data as Recommendation[]);
      setSells(s.data as Recommendation[]);
    } catch (e: unknown) {
      setDataError((e as { message?: string }).message || 'Failed to load');
    }
    setLoadingData(false);
  };

  useEffect(() => { loadFund(fund); }, [fund]);

  const lookupTicker = async () => {
    if (!symbol.trim()) return;
    setTickerLoading(true);
    setTickerError(null);
    setTickerData(null);
    try {
      const res = await getTicker(symbol.toUpperCase());
      setTickerData(res.data as Record<string, unknown>);
    } catch (e: unknown) {
      setTickerError((e as { message?: string }).message || 'Lookup failed');
    }
    setTickerLoading(false);
  };

  const startRun = async () => {
    setRunning(true);
    setRunError(null);
    try {
      const res = await runAnalysis(fund);
      const jobId = (res.data as { job_id: string }).job_id;
      for (let i = 0; i < 60; i++) {
        await new Promise(r => setTimeout(r, 3000));
        const status = await getAnalysisStatus(jobId);
        if (status.data.status === 'complete') {
          await loadFund(fund);
          break;
        }
        if (status.data.status === 'failed') {
          setRunError(status.data.error || 'Analysis failed');
          break;
        }
      }
    } catch (e: unknown) {
      setRunError((e as { message?: string }).message || 'Error');
    }
    setRunning(false);
  };

  const td = tickerData as {
    signal?: string; confidence?: number; reasons?: string[];
    fundamental?: { signal?: string; total_score?: number };
    technical?: { rsi?: number; macd?: number };
  } | null;

  return (
    <div style={{ padding: '1rem', maxWidth: 1000, margin: '0 auto' }}>
      <h1 style={{ color: '#e2e8f0', fontSize: '1.4rem', marginBottom: '1rem' }}>Analysis</h1>

      {/* Fund tabs */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
        {FUNDS.map(f => (
          <button key={f} onClick={() => setFund(f)}
            style={{
              background: fund === f ? '#0891b2' : '#1e293b',
              color: fund === f ? '#fff' : '#94a3b8',
              border: 'none', borderRadius: 8, padding: '0.4rem 1rem',
              cursor: 'pointer', fontSize: '0.85rem', textTransform: 'capitalize',
            }}>
            {f}
          </button>
        ))}
        <button onClick={startRun} disabled={running}
          style={{
            background: running ? '#1e293b' : '#334155', color: running ? '#64748b' : '#94a3b8',
            border: 'none', borderRadius: 8, padding: '0.4rem 1rem',
            cursor: running ? 'not-allowed' : 'pointer', fontSize: '0.85rem', marginLeft: 'auto',
          }}>
          {running ? 'Running…' : 'Re-run Analysis'}
        </button>
      </div>

      {runError && <ErrorBanner message={runError} />}
      {dataError && <ErrorBanner message={dataError} />}
      {loadingData && <LoadingSpinner />}

      {!loadingData && (
        <>
          <h3 style={{ color: '#00d4aa', fontSize: '0.95rem', marginBottom: '0.5rem' }}>Top Buys</h3>
          <RecTable items={buys} type="buys" />
          <h3 style={{ color: '#f87171', fontSize: '0.95rem', marginBottom: '0.5rem' }}>Top Sells</h3>
          <RecTable items={sells} type="sells" />
        </>
      )}

      {/* Ticker lookup */}
      <div style={{ marginTop: '2rem', background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: '1rem' }}>
        <h3 style={{ color: '#e2e8f0', fontSize: '1rem', marginBottom: '0.75rem' }}>Single Ticker Lookup</h3>
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.75rem' }}>
          <input value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && lookupTicker()}
            placeholder="e.g. AAPL"
            style={{ flex: 1, background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', borderRadius: 6, padding: '0.4rem 0.75rem', fontSize: '0.9rem' }} />
          <button onClick={lookupTicker} disabled={tickerLoading}
            style={{ background: '#0891b2', color: '#fff', border: 'none', borderRadius: 8, padding: '0.4rem 1rem', cursor: 'pointer' }}>
            Look up
          </button>
        </div>
        {tickerError && <ErrorBanner message={tickerError} />}
        {tickerLoading && <LoadingSpinner />}
        {td && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: '0.5rem' }}>
            {[
              ['Signal', td.signal ?? '—'],
              ['Confidence', td.confidence != null ? `${(td.confidence * 100).toFixed(0)}%` : '—'],
              ['Fund Signal', td.fundamental?.signal ?? '—'],
              ['Fund Score', td.fundamental?.total_score != null ? `${td.fundamental.total_score}/100` : '—'],
              ['RSI', td.technical?.rsi?.toFixed(1) ?? '—'],
              ['MACD', td.technical?.macd?.toFixed(3) ?? '—'],
            ].map(([k, v]) => (
              <div key={k as string} style={{ background: '#1e293b', borderRadius: 8, padding: '0.5rem 0.75rem' }}>
                <div style={{ color: '#64748b', fontSize: '0.72rem' }}>{k}</div>
                <div style={{ color: '#e2e8f0', fontWeight: 600 }}>{v}</div>
              </div>
            ))}
            {(td.reasons ?? []).length > 0 && (
              <div style={{ gridColumn: '1 / -1', background: '#1e293b', borderRadius: 8, padding: '0.5rem 0.75rem' }}>
                <div style={{ color: '#64748b', fontSize: '0.72rem', marginBottom: 4 }}>Reasons</div>
                {(td.reasons ?? []).map((r: string, i: number) => (
                  <div key={i} style={{ color: '#94a3b8', fontSize: '0.8rem' }}>• {r}</div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
