import { BrowserRouter, Routes, Route } from 'react-router-dom';
import NavBar from './components/NavBar';
import Screener from './pages/Screener';
import Backtest from './pages/Backtest';
import Analysis from './pages/Analysis';
import Portfolio from './pages/Portfolio';
import Config from './pages/Config';
import Report from './pages/Report';

export default function App() {
  return (
    <BrowserRouter>
      <div style={{ minHeight: '100vh', background: '#0d1117', color: '#e2e8f0', fontFamily: 'system-ui, -apple-system, sans-serif' }}>
        <NavBar />
        <Routes>
          <Route path="/" element={<Screener />} />
          <Route path="/backtest" element={<Backtest />} />
          <Route path="/analysis" element={<Analysis />} />
          <Route path="/portfolio" element={<Portfolio />} />
          <Route path="/config" element={<Config />} />
          <Route path="/report" element={<Report />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
