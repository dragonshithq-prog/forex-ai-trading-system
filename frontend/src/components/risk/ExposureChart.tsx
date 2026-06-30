'use client';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import type { ExposureData } from '@/types/market';

interface ExposureChartProps {
  data: ExposureData;
}

const COLORS = [
  '#3b82f6', '#22c55e', '#f59e0b', '#8b5cf6',
  '#ec4899', '#06b6d4', '#f97316', '#84cc16',
];

interface TooltipPayload {
  name: string;
  value: number;
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayload[] }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-card border border-border rounded px-2.5 py-1.5 text-xs shadow-xl">
      <p className="text-foreground font-semibold">{payload[0].name}</p>
      <p className="text-muted-foreground">{payload[0].value.toFixed(1)}%</p>
    </div>
  );
}

export function ExposureChart({ data }: ExposureChartProps) {
  const chartData = Object.entries(data.exposure_by_symbol).map(([symbol, value]) => ({
    name: symbol,
    value: parseFloat(value.toFixed(2)),
  }));

  if (!chartData.length) {
    return (
      <div className="h-full flex items-center justify-center text-xs text-muted-foreground">
        No exposure data
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <PieChart>
        <Pie
          data={chartData}
          cx="50%"
          cy="55%"
          innerRadius="45%"
          outerRadius="70%"
          paddingAngle={3}
          dataKey="value"
          strokeWidth={0}
        >
          {chartData.map((entry, index) => (
            <Cell
              key={entry.name}
              fill={COLORS[index % COLORS.length]}
              opacity={0.85}
            />
          ))}
        </Pie>
        <Tooltip content={<CustomTooltip />} />
        <Legend
          formatter={(value) => (
            <span style={{ fontSize: 10, color: '#71717a' }}>{value}</span>
          )}
          iconSize={8}
          iconType="circle"
          wrapperStyle={{ fontSize: 10 }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
