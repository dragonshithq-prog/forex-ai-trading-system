'use client';
import { motion } from 'framer-motion';
import { Shield, AlertTriangle, ShieldOff, TrendingDown } from 'lucide-react';
import { cn } from '@/lib/utils/cn';
import { useRiskState } from '@/lib/hooks/useRiskState';
import { formatPercent, formatCurrency, formatPnL } from '@/lib/utils/formatters';
import { getDrawdownColor, getPnLColor } from '@/lib/utils/colors';
import { CircuitBreakerStatus } from './CircuitBreakerStatus';
import { ExposureChart } from './ExposureChart';
import { MOCK_EXPOSURE } from '@/lib/mockData';

function GaugeBar({
  value,
  max,
  label,
  dangerThreshold = 80,
  warningThreshold = 60,
}: {
  value: number;
  max: number;
  label: string;
  dangerThreshold?: number;
  warningThreshold?: number;
}) {
  const pct = Math.min((value / max) * 100, 100);
  const color =
    pct >= dangerThreshold
      ? 'bg-loss'
      : pct >= warningThreshold
        ? 'bg-yellow-400'
        : 'bg-profit';

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-muted-foreground">{label}</span>
        <span className="text-xs font-mono font-medium text-foreground tabular-nums">
          {value.toFixed(1)}% / {max}%
        </span>
      </div>
      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
        <motion.div
          className={cn('h-full rounded-full', color)}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
          aria-hidden
        />
      </div>
    </div>
  );
}

export function RiskDashboard() {
  const { riskState, alerts } = useRiskState();

  const unacknowledgedAlerts = alerts.filter((a) => !a.acknowledged);

  if (!riskState) {
    return (
      <div className="space-y-3 animate-pulse">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-8 bg-muted rounded-md" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Circuit breaker */}
      <CircuitBreakerStatus isActive={riskState.is_circuit_breaker_active} reason={riskState.circuit_breaker_reason} />

      {/* Key metrics row */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-muted/30 rounded-lg p-3">
          <div className="flex items-center gap-1.5 mb-1">
            <TrendingDown className="w-3 h-3 text-muted-foreground" aria-hidden />
            <span className="text-[10px] text-muted-foreground uppercase tracking-wider">Drawdown</span>
          </div>
          <div className={cn('text-xl font-mono font-bold tabular-nums', getDrawdownColor(riskState.current_drawdown_pct))}>
            -{formatPercent(riskState.current_drawdown_pct)}
          </div>
          <div className="text-[10px] text-muted-foreground mt-0.5">
            Max: -{formatPercent(riskState.max_drawdown_pct)}
          </div>
        </div>

        <div className="bg-muted/30 rounded-lg p-3">
          <div className="flex items-center gap-1.5 mb-1">
            <Shield className="w-3 h-3 text-muted-foreground" aria-hidden />
            <span className="text-[10px] text-muted-foreground uppercase tracking-wider">Exposure</span>
          </div>
          <div className="text-xl font-mono font-bold text-foreground tabular-nums">
            {formatPercent(riskState.total_exposure_pct)}
          </div>
          <div className="text-[10px] text-muted-foreground mt-0.5">
            {riskState.open_positions} positions
          </div>
        </div>
      </div>

      {/* Gauge bars */}
      <div className="space-y-2.5">
        <GaugeBar
          label="Daily Drawdown"
          value={Math.abs(riskState.daily_pnl / (riskState.current_equity / 100))}
          max={3}
          dangerThreshold={85}
          warningThreshold={60}
        />
        <GaugeBar
          label="Total Exposure"
          value={riskState.total_exposure_pct}
          max={20}
          dangerThreshold={85}
          warningThreshold={60}
        />
        <GaugeBar
          label="Max Drawdown"
          value={riskState.current_drawdown_pct}
          max={15}
          dangerThreshold={80}
          warningThreshold={50}
        />
      </div>

      {/* P&L summary */}
      <div className="grid grid-cols-3 gap-2 text-center">
        {[
          { label: 'Daily', value: riskState.daily_pnl },
          { label: 'Weekly', value: riskState.weekly_pnl },
          { label: 'Monthly', value: riskState.monthly_pnl },
        ].map(({ label, value }) => (
          <div key={label} className="bg-muted/20 rounded-md p-2">
            <div className="text-[10px] text-muted-foreground mb-0.5">{label}</div>
            <div className={cn('text-xs font-mono font-semibold tabular-nums', getPnLColor(value))}>
              {formatPnL(value)}
            </div>
          </div>
        ))}
      </div>

      {/* Exposure chart */}
      <div className="h-36">
        <ExposureChart data={MOCK_EXPOSURE} />
      </div>

      {/* Active alerts */}
      {unacknowledgedAlerts.length > 0 && (
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5 text-xs text-warning font-medium">
            <AlertTriangle className="w-3.5 h-3.5" aria-hidden />
            {unacknowledgedAlerts.length} Active Alert{unacknowledgedAlerts.length !== 1 ? 's' : ''}
          </div>
          {unacknowledgedAlerts.slice(0, 2).map((alert) => (
            <div
              key={alert.id}
              className="text-xs bg-yellow-500/10 border border-yellow-500/20 text-yellow-300 rounded px-2.5 py-1.5"
              role="alert"
            >
              {alert.message}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
