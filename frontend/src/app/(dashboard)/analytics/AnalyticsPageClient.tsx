'use client';
import useSWR from 'swr';
import { api } from '@/lib/api';
import { EquityCurve } from '@/components/charts/EquityCurve';
import { MonthlyReturns } from '@/components/charts/MonthlyReturns';
import {
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
} from 'recharts';
import { formatPercent, formatNumber } from '@/lib/utils/formatters';
import { cn } from '@/lib/utils/cn';
import { PageLoader } from '@/components/common/LoadingSpinner';

function MetricRow({ label, value, positive = true }: { label: string; value: string; positive?: boolean }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-border/50 last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className={cn('text-sm font-mono font-semibold tabular-nums', positive ? 'text-foreground' : 'text-muted-foreground')}>
        {value}
      </span>
    </div>
  );
}

export function AnalyticsPageClient() {
  const { data: metrics, isLoading: metricsLoading } = useSWR(
    'portfolio-metrics',
    () => api.analytics.getPortfolioMetrics()
  );
  const { data: equityCurve, isLoading: curveLoading } = useSWR(
    'equity-curve',
    () => api.analytics.getEquityCurve()
  );
  const { data: monthlyReturns, isLoading: monthlyLoading } = useSWR(
    'monthly-returns',
    () => api.analytics.getMonthlyReturns()
  );

  if (metricsLoading || curveLoading) return <PageLoader />;

  const strategyData = [
    { name: 'ICT Momentum', trades: 87, winRate: 72.4, pnl: 4820 },
    { name: 'Mean Rev.', trades: 64, winRate: 68.8, pnl: 3240 },
    { name: 'Breakout', trades: 52, winRate: 59.6, pnl: 1980 },
    { name: 'Trend Follow', trades: 109, winRate: 65.1, pnl: 5410 },
  ];

  const pairData = [
    { pair: 'EURUSD', trades: 94, pnl: 5840, winRate: 71.3 },
    { pair: 'GBPJPY', trades: 63, pnl: 3290, winRate: 66.7 },
    { pair: 'USDJPY', trades: 58, pnl: 2140, winRate: 63.8 },
    { pair: 'AUDUSD', trades: 47, pnl: 1780, winRate: 59.6 },
    { pair: 'GBPUSD', trades: 50, pnl: -430, winRate: 48.0 },
  ];

  return (
    <div className="space-y-4 animate-fade-in">
      <div>
        <h1 className="text-xl font-bold text-foreground">Performance Analytics</h1>
        <p className="text-sm text-muted-foreground">Comprehensive trading performance analysis</p>
      </div>

      {/* Equity Curve */}
      <div className="bg-card border border-border rounded-lg p-4">
        <h2 className="text-sm font-semibold text-foreground mb-4">Equity Curve</h2>
        <div className="h-52">
          <EquityCurve data={equityCurve ?? []} isLoading={curveLoading} />
        </div>
      </div>

      {/* Key metrics grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Return metrics */}
        <div className="bg-card border border-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-foreground mb-3">Return Metrics</h2>
          <div className="space-y-0">
            <MetricRow label="Total Return" value={formatPercent(metrics?.total_return_pct ?? 0, 2, true)} />
            <MetricRow label="Sharpe Ratio" value={formatNumber(metrics?.sharpe_ratio ?? 0)} />
            <MetricRow label="Sortino Ratio" value={formatNumber(metrics?.sortino_ratio ?? 0)} />
            <MetricRow label="Calmar Ratio" value={formatNumber(metrics?.calmar_ratio ?? 0)} />
            <MetricRow label="Profit Factor" value={formatNumber(metrics?.profit_factor ?? 0)} />
          </div>
        </div>

        {/* Risk metrics */}
        <div className="bg-card border border-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-foreground mb-3">Risk Metrics</h2>
          <div className="space-y-0">
            <MetricRow label="Max Drawdown" value={`-${formatPercent(metrics?.max_drawdown_pct ?? 0)}`} positive={false} />
            <MetricRow label="Current Drawdown" value={`-${formatPercent(metrics?.current_drawdown_pct ?? 0)}`} positive={false} />
            <MetricRow label="Recovery Factor" value={formatNumber(metrics?.recovery_factor ?? 0)} />
            <MetricRow label="Best Trade" value={formatPercent(metrics?.best_trade_pct ?? 0, 2, true)} />
            <MetricRow label="Worst Trade" value={`${formatPercent(metrics?.worst_trade_pct ?? 0, 2, true)}`} positive={false} />
          </div>
        </div>

        {/* Trade stats */}
        <div className="bg-card border border-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-foreground mb-3">Trade Statistics</h2>
          <div className="space-y-0">
            <MetricRow label="Win Rate" value={formatPercent(metrics?.win_rate ?? 0)} />
            <MetricRow label="Total Trades" value={(metrics?.total_trades ?? 0).toString()} />
            <MetricRow label="Avg Win" value={formatPercent(metrics?.avg_win_pct ?? 0, 2, true)} />
            <MetricRow label="Avg Loss" value={formatPercent(metrics?.avg_loss_pct ?? 0, 2, true)} positive={false} />
            <MetricRow label="Expectancy" value={formatPercent(metrics?.expectancy ?? 0, 2, true)} />
          </div>
        </div>
      </div>

      {/* Monthly returns heatmap */}
      <div className="bg-card border border-border rounded-lg p-4">
        <h2 className="text-sm font-semibold text-foreground mb-4">Monthly Returns Heatmap</h2>
        {monthlyLoading ? (
          <div className="h-32 animate-pulse bg-muted/20 rounded-lg" />
        ) : (
          <MonthlyReturns data={monthlyReturns ?? {}} />
        )}
      </div>

      {/* Strategy + Pair performance */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Strategy performance */}
        <div className="bg-card border border-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-foreground mb-4">Strategy Performance</h2>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={strategyData} layout="vertical" margin={{ left: 8, right: 8, top: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(0 0% 13%)" horizontal={false} />
                <XAxis type="number" tick={{ fill: '#71717a', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis dataKey="name" type="category" width={80} tick={{ fill: '#71717a', fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={{
                    background: 'hsl(0 0% 9%)',
                    border: '1px solid hsl(0 0% 13%)',
                    borderRadius: 8,
                    fontSize: 11,
                    color: '#f2f2f2',
                  }}
                />
                <Bar dataKey="pnl" radius={[0, 4, 4, 0]}>
                  {strategyData.map((entry, i) => (
                    <Cell key={i} fill={entry.pnl >= 0 ? '#22c55e' : '#ef4444'} opacity={0.8} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Pair performance table */}
        <div className="bg-card border border-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-foreground mb-4">Pair Performance</h2>
          <table className="w-full text-xs" role="table">
            <thead>
              <tr className="border-b border-border">
                {['Pair', 'Trades', 'Win Rate', 'Net P&L'].map((h) => (
                  <th key={h} className="text-left pb-2 text-muted-foreground font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pairData.map((row) => (
                <tr key={row.pair} className="border-b border-border/30 hover:bg-muted/10">
                  <td className="py-2 font-mono font-semibold text-foreground">{row.pair}</td>
                  <td className="py-2 text-muted-foreground">{row.trades}</td>
                  <td className={cn('py-2 font-mono tabular-nums', row.winRate >= 55 ? 'text-profit' : 'text-muted-foreground')}>
                    {formatPercent(row.winRate)}
                  </td>
                  <td className={cn('py-2 font-mono font-semibold tabular-nums', row.pnl >= 0 ? 'text-profit' : 'text-loss')}>
                    {row.pnl >= 0 ? '+' : ''}{row.pnl}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
