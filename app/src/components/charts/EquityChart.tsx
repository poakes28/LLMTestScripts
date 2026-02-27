import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from 'recharts';
import type { EquityCurvePoint } from '../../types';

interface Props {
  data: EquityCurvePoint[];
  benchmarkData?: { date: string; value: number }[];
  initialCapital: number;
}

export default function EquityChart({ data, initialCapital }: Props) {
  const chartData = data.map(d => ({
    date: d.date.slice(5),  // MM-DD
    value: d.total_value,
    pct: ((d.total_value / initialCapital - 1) * 100).toFixed(2),
  }));

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 11 }} />
        <YAxis
          tickFormatter={v => `$${(v / 1000).toFixed(0)}k`}
          tick={{ fill: '#64748b', fontSize: 11 }}
          width={55}
        />
        <Tooltip
          contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6 }}
          labelStyle={{ color: '#94a3b8' }}
          formatter={(v) => [`$${Number(v ?? 0).toLocaleString()}`, 'Portfolio'] as [string, string]}
        />
        <Legend wrapperStyle={{ color: '#94a3b8', fontSize: 12 }} />
        <Line
          type="monotone" dataKey="value" name="Portfolio"
          stroke="#00d4aa" strokeWidth={2} dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
