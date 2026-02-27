import { useState, useEffect } from 'react';
import { getConfig, putConfig } from '../api/client';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorBanner from '../components/ErrorBanner';

const SECTIONS = ['technical', 'fundamental', 'backtest', 'screener', 'llm'];

function toast(msg: string) {
  const el = document.createElement('div');
  el.textContent = msg;
  Object.assign(el.style, {
    position: 'fixed', bottom: '1rem', right: '1rem',
    background: '#00d4aa', color: '#000', padding: '0.5rem 1rem',
    borderRadius: 8, fontWeight: 600, zIndex: '9999', fontSize: '0.875rem',
  });
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

export default function Config() {
  const [section, setSection] = useState('technical');
  const [data, setData] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async (s: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await getConfig(s);
      setData(res.data as Record<string, unknown>);
    } catch (e: unknown) {
      setError((e as { message?: string }).message || 'Load failed');
    }
    setLoading(false);
  };

  useEffect(() => { load(section); }, [section]);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await putConfig(section, data);
      toast('Saved ✓');
    } catch (e: unknown) {
      setError((e as { message?: string }).message || 'Save failed');
    }
    setSaving(false);
  };

  const renderField = (key: string, value: unknown) => {
    const label = key.replace(/_/g, ' ');

    if (typeof value === 'boolean') {
      return (
        <label key={key} style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#94a3b8', fontSize: '0.85rem', cursor: 'pointer' }}>
          <input type="checkbox" checked={value}
            onChange={e => setData(d => ({ ...d, [key]: e.target.checked }))} />
          {label}
        </label>
      );
    }

    if (typeof value === 'number') {
      return (
        <label key={key} style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: '0.8rem', color: '#94a3b8' }}>
          {label}
          <input type="number" value={value}
            step={value < 10 ? 0.01 : value < 1000 ? 1 : 1000}
            onChange={e => setData(d => ({ ...d, [key]: parseFloat(e.target.value) }))}
            style={{ background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', borderRadius: 6, padding: '0.4rem' }} />
        </label>
      );
    }

    if (typeof value === 'string') {
      return (
        <label key={key} style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: '0.8rem', color: '#94a3b8' }}>
          {label}
          <input type="text" value={value}
            onChange={e => setData(d => ({ ...d, [key]: e.target.value }))}
            style={{ background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', borderRadius: 6, padding: '0.4rem' }} />
        </label>
      );
    }

    if (value === null || value === undefined) {
      return (
        <label key={key} style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: '0.8rem', color: '#94a3b8' }}>
          {label}
          <input type="text" value=""
            onChange={e => {
              const v = e.target.value;
              setData(d => ({ ...d, [key]: v === '' ? null : isNaN(parseFloat(v)) ? v : parseFloat(v) }));
            }}
            placeholder="null"
            style={{ background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', borderRadius: 6, padding: '0.4rem' }} />
        </label>
      );
    }

    // Arrays and objects — show as JSON textarea
    return (
      <label key={key} style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: '0.8rem', color: '#94a3b8', gridColumn: '1 / -1' }}>
        {label}
        <textarea rows={3}
          value={JSON.stringify(value, null, 2)}
          onChange={e => {
            try { setData(d => ({ ...d, [key]: JSON.parse(e.target.value) })); } catch { /* ignore */ }
          }}
          style={{ background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', borderRadius: 6, padding: '0.4rem', resize: 'vertical', fontFamily: 'monospace', fontSize: '0.8rem' }} />
      </label>
    );
  };

  return (
    <div style={{ padding: '1rem', maxWidth: 900, margin: '0 auto' }}>
      <h1 style={{ color: '#e2e8f0', fontSize: '1.4rem', marginBottom: '1rem' }}>Configuration</h1>

      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
        {SECTIONS.map(s => (
          <button key={s} onClick={() => setSection(s)}
            style={{
              background: section === s ? '#0891b2' : '#1e293b',
              color: section === s ? '#fff' : '#94a3b8',
              border: 'none', borderRadius: 8, padding: '0.4rem 1rem',
              cursor: 'pointer', fontSize: '0.85rem', textTransform: 'capitalize',
            }}>
            {s}
          </button>
        ))}
      </div>

      {loading && <LoadingSpinner />}
      {error && <ErrorBanner message={error} />}

      {!loading && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '0.75rem', marginBottom: '1.5rem' }}>
            {Object.entries(data).map(([k, v]) => renderField(k, v))}
          </div>

          <button onClick={save} disabled={saving}
            style={{
              background: saving ? '#1e293b' : '#00d4aa', color: '#000',
              border: 'none', borderRadius: 8, padding: '0.6rem 1.5rem',
              fontWeight: 700, fontSize: '0.95rem', cursor: saving ? 'not-allowed' : 'pointer',
            }}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        </>
      )}
    </div>
  );
}
