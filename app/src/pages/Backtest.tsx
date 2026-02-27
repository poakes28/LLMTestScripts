import { useState, useEffect } from 'react';
import { startScreenBacktest, getBacktestStatus } from '../api/client';
import type { ScreenBacktestResponse, IndividualReturn } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorBanner from '../components/ErrorBanner';
import EquityChart from '../components/charts/EquityChart';

const today = () => new Date().toISOString().slice(0, 10);
const ago = (days: number) => new Date(Date.now() - days * 86400_000).toISOString().slice(0, 10);

function MetricCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={{ background: '#1e293b', borderRadius: 10, padding: '0.75rem 1rem', flex: '1 1 120px' }}>
      <div style={{ color: '#64748b', fontSize: '0.75rem', marginBottom: 4 }}>{label}</div>
      <div style={{ color: '#e2e8f0', fontSize: '1.2rem', fontWeight: 700 }}>{value}</div>
      {sub && <div style={{ color: '#94a3b8', fontSize: '0.75rem' }}>{sub}</div>}
    </div>
  );
}

const pctColor = (v: number) => v >= 0 ? '#00d4aa' : '#f87171';

export default function Backtest() {
  const [tickers, setTickers] = useState('');
  const [startDate, setStartDate] = useState(ago(180));
  const [endDate, setEndDate] = useState(today());
  const [capital, setCapital] = useState(10000);
  const [holdMode, setHoldMode] = useState<'fixed' | 'criteria_exit'>('fixed');
  const [holdDays, setHoldDays] = useState(60);
  const [benchmark, setBenchmark] = useState('SPY');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ScreenBacktestResponse | null>(null);

  // Pre-fill tickers from screener via localStorage
  useEffect(() => {
    const saved = localStorage.getItem('backtest_tickers');
    if (saved) {
      setTickers(saved);
      localStorage.removeItem('backtest_tickers');
    }
  }, []);

  const poll = async (jobId: string) => {
    for (let i = 0; i < 120; i++) {
      await new Promise(r => setTimeout(r, 2000));
      const res = await getBacktestStatus(jobId);
      if (res.data.status === 'complete') {
        setResult(res.data.result as ScreenBacktestResponse);
        setLoading(false);
        return;
      }
      if (res.data.status === 'failed') {
        setError(res.data.error || 'Backtest failed');
        setLoading(false);
        return;
      }
    }
    setError('Backtest timed out');
    setLoading(false);
  };

  const run = async () => {
    const tickerList = tickers.split(/[\s,\n]+/).map(t => t.trim().toUpperCase()).filter(Boolean);
    if (!tickerList.length) { setError('Enter at least one ticker'); return; }
    setError(null);
    setLoading(true);
    setResult(null);
    try {
      const res = await startScreenBacktest({
        tickers: tickerList, start_date: startDate, end_date: endDate,
        initial_capital: capital, hold_mode: holdMode, hold_period_days: holdDays, benchmark,
      });
      await poll(res.data.job_id);
    } catch (e: unknown) {
      setError((e as { message?: string }).message || 'Network error');
      setLoading(false);
    }
  };

  const sorted = result
    ? [...result.individual_returns].sort((a, b) => b.return_pct - a.return_pct)
    : [];

  return (
    <div style={{ padding: '1rem', maxWidth: 1200, margin: '0 auto' }}>
      <h1 style={{ color: '#e2e8f0', fontSize: '1.4rem', marginBottom: '1rem' }}>Screen Backtest</h1>

      {/* Warning */}
      <div style={{ background: '#1c1005', border: '1px solid #78350f', borderRadius: 8, padding: '0.6rem 1rem', marginBottom: '1rem', color: '#fcd34d', fontSize: '0.8rem' }}>
        ⚠️ Survivorship & look-ahead bias: fundamental metrics reflect <em>current</em> values, not historical. Technical indicator backtesting is historically accurate.
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: '0.75rem', marginBottom: '1rem' }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: '0.8rem', color: '#94a3b8' }}>
          Start Date
          <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)}
            style={{ background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', borderRadius: 6, padding: '0.4rem' }} />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: '0.8rem', color: '#94a3b8' }}>
          End Date
          <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)}
            style={{ background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', borderRadius: 6, padding: '0.4rem' }} />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: '0.8rem', color: '#94a3b8' }}>
          Capital ($)
          <input type="number" value={capital} onChange={e => setCapital(parseFloat(e.target.value))}
            style={{ background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', borderRadius: 6, padding: '0.4rem' }} />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: '0.8rem', color: '#94a3b8' }}>
          Benchmark
          <input value={benchmark} onChange={e => setBenchmark(e.target.value.toUpperCase())}
            style={{ background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', borderRadius: 6, padding: '0.4rem' }} />
        </label>
      </div>

      <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.75rem' }}>
        Tickers (one per line or comma-separated)
        <textarea rows={4} value={tickers} onChange={e => setTickers(e.target.value)}
          placeholder="AAPL&#10;MSFT&#10;GOOGL"
          style={{ background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', borderRadius: 6, padding: '0.4rem', resize: 'vertical' }} />
      </label>

      <div style={{ display: 'flex', gap: '1.5rem', marginBottom: '1rem', alignItems: 'center' }}>
        <label style={{ display: 'flex', gap: 8, alignItems: 'center', color: '#94a3b8', fontSize: '0.85rem', cursor: 'pointer' }}>
          <input type="radio" name="hold" value="fixed" checked={holdMode === 'fixed'} onChange={() => setHoldMode('fixed')} />
          Fixed Duration
        </label>
        <label style={{ display: 'flex', gap: 8, alignItems: 'center', color: '#94a3b8', fontSize: '0.85rem', cursor: 'pointer' }}>
          <input type="radio" name="hold" value="criteria_exit" checked={holdMode === 'criteria_exit'} onChange={() => setHoldMode('criteria_exit')} />
          Criteria Exit (tech signals)
        </label>
        {holdMode === 'fixed' && (
          <label style={{ display: 'flex', gap: 8, alignItems: 'center', color: '#94a3b8', fontSize: '0.85rem' }}>
            Days:
            <input type="number" value={holdDays} onChange={e => setHoldDays(parseInt(e.target.value))}
              style={{ width: 70, background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', borderRadius: 6, padding: '0.3rem' }} />
          </label>
        )}
      </div>

      <button onClick={run} disabled={loading}
        style={{
          background: loading ? '#1e293b' : '#0891b2', color: '#fff',
          border: 'none', borderRadius: 8, padding: '0.6rem 1.5rem',
          fontSize: '0.95rem', cursor: loading ? 'not-allowed' : 'pointer',
          marginBottom: '1rem',
        }}>
        {loading ? 'Running Backtest…' : 'Run Backtest'}
      </button>

      {error && <ErrorBanner message={error} />}
      {loading && <LoadingSpinner label="Downloading price data and running simulation…" />}

      {result && (
        <>
          {result.warnings?.length > 0 && (
            <div style={{ background: '#1c1005', border: '1px solid #78350f', borderRadius: 8, padding: '0.5rem 1rem', marginBottom: '1rem', color: '#fcd34d', fontSize: '0.8rem' }}>
              {result.warnings.map((w, i) => <div key={i}>⚠️ {w}</div>)}
            </div>
          )}

          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginBottom: '1.5rem' }}>
            <MetricCard label="Total Return"
              value={`${(result.metrics.total_return * 100).toFixed(2)}%`}
              sub={`$${result.initial_capital.toLocaleString()} → $${result.final_value.toLocaleString()}`} />
            <MetricCard label="Sharpe Ratio" value={result.metrics.sharpe_ratio?.toFixed(2) ?? '—'} />
            <MetricCard label="Max Drawdown" value={`${(result.metrics.max_drawdown * 100).toFixed(2)}%`} />
            <MetricCard label="Volatility" value={`${((result.metrics.annual_volatility ?? 0) * 100).toFixed(1)}%`} />
            {result.benchmark_metrics?.total_return != null && (
              <MetricCard label={`${result.benchmark} Return`}
                value={`${(result.benchmark_metrics.total_return * 100).toFixed(2)}%`} />
            )}
          </div>

          <div style={{ marginBottom: '1.5rem' }}>
            <h3 style={{ color: '#94a3b8', fontSize: '0.9rem', marginBottom: '0.5rem' }}>Equity Curve</h3>
            <EquityChart data={result.equity_curve} initialCapital={result.initial_capital} />
          </div>

          <div style={{ overflowX: 'auto' }}>
            <h3 style={{ color: '#94a3b8', fontSize: '0.9rem', marginBottom: '0.5rem' }}>Individual Returns</h3>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
              <thead>
                <tr style={{ background: '#0f172a', color: '#64748b' }}>
                  {['Ticker', 'Entry Date', 'Exit Date', 'Entry $', 'Exit $', 'Return %', 'Days', 'Reason'].map(h => (
                    <th key={h} style={{ padding: '0.5rem', textAlign: 'left' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sorted.map((r: IndividualReturn, i: number) => (
                  <tr key={r.ticker} style={{ background: i % 2 === 0 ? '#0f172a' : '#1a2332' }}>
                    <td style={{ padding: '0.4rem 0.5rem', color: '#e2e8f0', fontWeight: 600 }}>{r.ticker}</td>
                    <td style={{ padding: '0.4rem 0.5rem', color: '#94a3b8' }}>{r.entry_date}</td>
                    <td style={{ padding: '0.4rem 0.5rem', color: '#94a3b8' }}>{r.exit_date}</td>
                    <td style={{ padding: '0.4rem 0.5rem', color: '#94a3b8' }}>${r.entry_price.toFixed(2)}</td>
                    <td style={{ padding: '0.4rem 0.5rem', color: '#94a3b8' }}>${r.exit_price.toFixed(2)}</td>
                    <td style={{ padding: '0.4rem 0.5rem', color: pctColor(r.return_pct), fontWeight: 600 }}>
                      {(r.return_pct * 100).toFixed(2)}%
                    </td>
                    <td style={{ padding: '0.4rem 0.5rem', color: '#94a3b8' }}>{r.hold_days}</td>
                    <td style={{ padding: '0.4rem 0.5rem', color: '#64748b' }}>{r.exit_reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
