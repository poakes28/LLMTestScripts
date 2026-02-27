import { NavLink } from 'react-router-dom';

const links = [
  { to: '/', label: 'Screener' },
  { to: '/backtest', label: 'Backtest' },
  { to: '/analysis', label: 'Analysis' },
  { to: '/portfolio', label: 'Portfolio' },
  { to: '/config', label: 'Config' },
  { to: '/report', label: 'Report' },
];

export default function NavBar() {
  return (
    <nav style={{
      background: '#0f172a',
      borderBottom: '1px solid #1e293b',
      padding: '0.5rem 1rem',
      display: 'flex',
      gap: '0.25rem',
      overflowX: 'auto',
      WebkitOverflowScrolling: 'touch',
      position: 'sticky',
      top: 0,
      zIndex: 100,
    }}>
      {links.map(({ to, label }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          style={({ isActive }) => ({
            padding: '0.4rem 0.75rem',
            borderRadius: 6,
            textDecoration: 'none',
            fontSize: '0.85rem',
            fontWeight: 500,
            whiteSpace: 'nowrap',
            color: isActive ? '#00d4aa' : '#94a3b8',
            background: isActive ? '#1e293b' : 'transparent',
            transition: 'all 0.15s',
          })}
        >
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
