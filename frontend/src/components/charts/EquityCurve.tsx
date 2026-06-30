'use client';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { formatCurrency, formatDate, getMonthYear } from '@/lib/utils/formatters';
import type { EquityPoint } from '@/types/api';

interface EquityCurveProps {
  data: EquityPoint[];
  isLoading?: boolean;
}

interface TooltipPayload {
  value: number;
  payload: EquityPoint;
}

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: TooltipPayload[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload as EquityPoint;
  return (
    <div className="bg-card border border-border rounded-lg p-3 shadow-xl text-xs">
      <p className="text-muted-foreground mb-2">{formatDate(point.timestamp)}</p>
      <p className="font-mono font-semibold text-foreground">
        {formatCurrency(point.equity)}
      </p>
      <p className="text-loss font-mono">
        DD: -{point.drawdown_pct.toFixed(2)}%
      </p>
    </div>
  );
}

export function EquityCurve({ data, isLoading }: EquityCurveProps) {
  if (isLoading) {
    return (
      <div className="h-full bg-muted/10 rounded-lg animate-pulse flex items-center justify-center">
        <span className="text-xs text-muted-foreground">Loading chart...</span>
      </div>
    );
  }

  if (!data.length) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-xs text-muted-foreground">No equity data available</p>
      </div>
    );
  }

  const startEquity = data[0]?.equity ?? 0;
  const tickFormatter = (v: number) => `$${(v / 1000).toFixed(0)}k`;
  const labelFormatter = (ts: string) => getMonthYear(ts);

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#22c55e" stopOpacity={0.2} />
            <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="drawdownGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#ef4444" stopOpacity={0.2} />
            <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
          </linearGradient>
        </defs>

        <CartesianGrid
          strokeDasharray="3 3"
          stroke="hsl(0 0% 13%)"
          vertical={false}
        />

        <XAxis
          dataKey="timestamp"
          tickFormatter={labelFormatter}
          tick={{ fill: '#71717a', fontSize: 10 }}
          axisLine={{ stroke: '#222' }}
          tickLine={false}
          interval="preserveStartEnd"
        />

        <YAxis
          tickFormatter={tickFormatter}
          tick={{ fill: '#71717a', fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          width={50}
        />

        <Tooltip content={<CustomTooltip />} />

        <ReferenceLine
          y={startEquity}
          stroke="#444"
          strokeDasharray="4 4"
          strokeWidth={1}
        />

        <Area
          type="monotone"
          dataKey="equity"
          stroke="#22c55e"
          strokeWidth={1.5}
          fill="url(#equityGradient)"
          dot={false}
          activeDot={{ r: 4, fill: '#22c55e', stroke: '#0a0a0a', strokeWidth: 2 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
