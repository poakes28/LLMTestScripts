import { useState, useEffect } from 'react';
import { getAllPortfolios } from '../api/client';
import type { PortfolioSummary, Position } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorBanner from '../components/ErrorBanner';

const pctColor = (v: number) => ({ color: v >= 0 ? '#00d4aa' : '#f87171' });
const fmt$ = (v?: number) => v != null ? `$${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—';
const fmtPct = (v?: number) => v != null ? `${(v * 100).toFixed(2)}%` : '—';

export default function Portfolio() {
  const [portfolios, setPortfolios] = useState<Record<string, PortfolioSummary>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fund, setFund] = useState('');

  useEffect(() => {
    getAllPortfolios()
      .then(res => {
        const data = res.data as Record<string, PortfolioSummary>;
        setPortfolios(data);
        const keys = Object.keys(data);
        if (keys.length) setFund(keys[0]);
      })
      .catch(e => setError(e.message || 'Failed to load'))
      .finally(() => setLoading(false));
  }, []);

  const current = portfolios[fund];

  return (
    <div style={{ padding: '1rem', maxWidth: 900, margin: '0 auto' }}>
      <h1 style={{ color: '#e2e8f0', fontSize: '1.4rem', marginBottom: '1rem' }}>Portfolio</h1>

      {loading && <LoadingSpinner />}
      {error && <ErrorBanner message={error} />}

      {/* Fund tabs */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
        {Object.keys(portfolios).map(f => (
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
      </div>

      {current && (
        <>
          {/* Summary cards */}
          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginBottom: '1.5rem' }}>
            {[
              ['Total Value', fmt$(current.total_value)],
              ['Cash', fmt$(current.cash)],
              ['Invested', fmt$(current.invested_value)],
              ['Unrealized P&L', `${fmt$(current.unrealized_pnl)} (${fmtPct(current.unrealized_pnl_pct)})`],
              ['Positions', String(current.num_positions)],
            ].map(([k, v]) => (
              <div key={k} style={{ background: '#1e293b', borderRadius: 10, padding: '0.75rem 1rem', flex: '1 1 120px' }}>
                <div style={{ color: '#64748b', fontSize: '0.75rem', marginBottom: 4 }}>{k}</div>
                <div style={{ color: k === 'Unrealized P&L' ? (current.unrealized_pnl >= 0 ? '#00d4aa' : '#f87171') : '#e2e8f0', fontSize: '1rem', fontWeight: 700 }}>{v}</div>
              </div>
            ))}
          </div>

          {/* Positions table */}
          {(current.positions ?? []).length > 0 ? (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                <thead>
                  <tr style={{ background: '#0f172a', color: '#64748b' }}>
                    {['Ticker', 'Qty', 'Avg Cost', 'Price', 'Mkt Value', 'P&L', 'P&L %'].map(h => (
                      <th key={h} style={{ padding: '0.5rem', textAlign: 'left' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {current.positions.map((p: Position, i: number) => (
                    <tr key={p.ticker} style={{ background: i % 2 === 0 ? '#0f172a' : '#1a2332' }}>
                      <td style={{ padding: '0.4rem 0.5rem', color: '#e2e8f0', fontWeight: 600 }}>{p.ticker}</td>
                      <td style={{ padding: '0.4rem 0.5rem', color: '#94a3b8' }}>{p.quantity}</td>
                      <td style={{ padding: '0.4rem 0.5rem', color: '#94a3b8' }}>{fmt$(p.avg_cost)}</td>
                      <td style={{ padding: '0.4rem 0.5rem', color: '#94a3b8' }}>{fmt$(p.current_price)}</td>
                      <td style={{ padding: '0.4rem 0.5rem', color: '#e2e8f0' }}>{fmt$(p.market_value)}</td>
                      <td style={{ padding: '0.4rem 0.5rem', ...pctColor(p.unrealized_pnl ?? 0) }}>{fmt$(p.unrealized_pnl)}</td>
                      <td style={{ padding: '0.4rem 0.5rem', ...pctColor(p.unrealized_pnl_pct ?? 0) }}>{fmtPct(p.unrealized_pnl_pct)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p style={{ color: '#64748b' }}>No open positions.</p>
          )}
        </>
      )}
    </div>
  );
}
