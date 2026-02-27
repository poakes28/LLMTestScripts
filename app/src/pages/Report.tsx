import { useState, useEffect } from 'react';
import { generateReport, getLatestReport } from '../api/client';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorBanner from '../components/ErrorBanner';

export default function Report() {
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reportUrl, setReportUrl] = useState<string | null>(null);
  const [reportDate, setReportDate] = useState<string | null>(null);

  useEffect(() => {
    getLatestReport()
      .then(res => {
        const r = res.data as { url?: string; filename?: string; generated_at?: string };
        if (r?.url) { setReportUrl(r.url); setReportDate(r.generated_at || null); }
      })
      .catch(() => {});
  }, []);

  const generate = async () => {
    setGenerating(true);
    setError(null);
    try {
      const res = await generateReport();
      const r = res.data as { url?: string; filename?: string; generated_at?: string };
      if (r?.url) { setReportUrl(r.url); setReportDate(r.generated_at || null); }
    } catch (e: unknown) {
      setError((e as { message?: string }).message || 'Report generation failed');
    }
    setGenerating(false);
  };

  return (
    <div style={{ padding: '1rem', maxWidth: 1200, margin: '0 auto' }}>
      <h1 style={{ color: '#e2e8f0', fontSize: '1.4rem', marginBottom: '1rem' }}>Report</h1>

      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', marginBottom: '1rem' }}>
        <button onClick={generate} disabled={generating}
          style={{
            background: generating ? '#1e293b' : '#0891b2', color: '#fff',
            border: 'none', borderRadius: 8, padding: '0.6rem 1.5rem',
            fontSize: '0.95rem', cursor: generating ? 'not-allowed' : 'pointer',
          }}>
          {generating ? 'Generating…' : 'Generate Report'}
        </button>
        {reportDate && <span style={{ color: '#64748b', fontSize: '0.8rem' }}>Last: {reportDate}</span>}
        {reportUrl && (
          <a href={reportUrl} target="_blank" rel="noreferrer"
            style={{ color: '#00d4aa', fontSize: '0.85rem' }}>
            Open in new tab
          </a>
        )}
      </div>

      {error && <ErrorBanner message={error} />}
      {generating && <LoadingSpinner label="Generating HTML report…" />}

      {reportUrl && !generating && (
        <iframe
          src={reportUrl}
          style={{
            width: '100%',
            height: 'calc(100vh - 180px)',
            border: '1px solid #1e293b',
            borderRadius: 10,
            background: '#fff',
          }}
          title="Trading System Report"
        />
      )}

      {!reportUrl && !generating && (
        <p style={{ color: '#64748b', fontSize: '0.9rem' }}>
          No report yet. Click "Generate Report" to create one.
        </p>
      )}
    </div>
  );
}
