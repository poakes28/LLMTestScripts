export default function ErrorBanner({ message }: { message: string }) {
  return (
    <div style={{
      background: '#450a0a', border: '1px solid #7f1d1d', borderRadius: 8,
      padding: '0.75rem 1rem', color: '#fca5a5', marginBottom: '1rem',
      fontSize: '0.9rem',
    }}>
      ⚠️ {message}
    </div>
  );
}
