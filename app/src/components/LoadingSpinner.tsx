export default function LoadingSpinner({ label = 'Loading...' }: { label?: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '2rem', gap: '0.75rem' }}>
      <div style={{
        width: 40, height: 40,
        border: '4px solid #334155',
        borderTop: '4px solid #00d4aa',
        borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
      }} />
      <span style={{ color: '#94a3b8', fontSize: '0.9rem' }}>{label}</span>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
