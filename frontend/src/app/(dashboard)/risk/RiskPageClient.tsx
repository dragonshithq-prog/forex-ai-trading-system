'use client';
import { useState } from 'react';
import useSWR from 'swr';
import { Shield, AlertTriangle, CheckCircle, Settings } from 'lucide-react';
import { api } from '@/lib/api';
import { CircuitBreakerStatus } from '@/components/risk/CircuitBreakerStatus';
import { ExposureChart } from '@/components/risk/ExposureChart';
import { useRiskState, useRiskConfig } from '@/lib/hooks/useRiskState';
import { formatPercent, formatCurrency, formatPnL, formatDateTime } from '@/lib/utils/formatters';
import { getAlertColor, getPnLColor, getDrawdownColor } from '@/lib/utils/colors';
import { cn } from '@/lib/utils/cn';
import { MOCK_EXPOSURE } from '@/lib/mockData';
import { toast } from 'sonner';

function ConfigInput({
  label,
  value,
  unit = '%',
  onChange,
}: {
  label: string;
  value: number;
  unit?: string;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-border/50 last:border-0">
      <label className="text-sm text-muted-foreground">{label}</label>
      <div className="flex items-center gap-1.5">
        <input
          type="number"
          value={value}
          step={unit === '%' ? 0.1 : 1}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          className="w-20 bg-muted border border-border rounded px-2 py-1 text-xs font-mono text-right text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          aria-label={label}
        />
        <span className="text-xs text-muted-foreground w-4">{unit}</span>
      </div>
    </div>
  );
}

export function RiskPageClient() {
  const { riskState, alerts } = useRiskState();
  const { config: riskConfig, refresh: refreshConfig } = useRiskConfig();
  const [localConfig, setLocalConfig] = useState<Record<string, number>>({});
  const [isSaving, setIsSaving] = useState(false);

  const handleConfigSave = async () => {
    setIsSaving(true);
    try {
      await api.risk.updateConfig(localConfig);
      refreshConfig();
      setLocalConfig({});
      toast.success('Risk configuration saved');
    } catch {
      toast.error('Failed to save risk configuration');
    } finally {
      setIsSaving(false);
    }
  };

  const cfg = { ...riskConfig, ...localConfig };

  return (
    <div className="space-y-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground">Risk Management</h1>
          <p className="text-sm text-muted-foreground">Monitor and configure trading risk parameters</p>
        </div>
      </div>

      {/* Circuit breaker + state */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Current state */}
        <div className="lg:col-span-2 space-y-4">
          {riskState && (
            <>
              <CircuitBreakerStatus
                isActive={riskState.is_circuit_breaker_active}
                reason={riskState.circuit_breaker_reason}
                activeUntil={riskState.circuit_breaker_until}
              />

              {/* State metrics */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  {
                    label: 'Current DD',
                    value: `-${formatPercent(riskState.current_drawdown_pct)}`,
                    color: getDrawdownColor(riskState.current_drawdown_pct),
                  },
                  {
                    label: 'Max DD',
                    value: `-${formatPercent(riskState.max_drawdown_pct)}`,
                    color: 'text-muted-foreground',
                  },
                  {
                    label: 'Exposure',
                    value: formatPercent(riskState.total_exposure_pct),
                    color: 'text-foreground',
                  },
                  {
                    label: 'Positions',
                    value: riskState.open_positions.toString(),
                    color: 'text-foreground',
                  },
                  {
                    label: 'Daily P&L',
                    value: formatPnL(riskState.daily_pnl),
                    color: getPnLColor(riskState.daily_pnl),
                  },
                  {
                    label: 'Weekly P&L',
                    value: formatPnL(riskState.weekly_pnl),
                    color: getPnLColor(riskState.weekly_pnl),
                  },
                  {
                    label: 'Consec. Losses',
                    value: riskState.consecutive_losses.toString(),
                    color: riskState.consecutive_losses >= 3 ? 'text-loss' : 'text-foreground',
                  },
                  {
                    label: 'Daily Trades',
                    value: riskState.daily_trades.toString(),
                    color: 'text-foreground',
                  },
                ].map(({ label, value, color }) => (
                  <div key={label} className="bg-card border border-border rounded-lg p-3">
                    <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">{label}</div>
                    <div className={cn('text-lg font-mono font-bold tabular-nums', color)}>{value}</div>
                  </div>
                ))}
              </div>

              {/* Exposure chart */}
              <div className="bg-card border border-border rounded-lg p-4">
                <h2 className="text-sm font-semibold text-foreground mb-3">Exposure by Symbol</h2>
                <div className="h-48">
                  <ExposureChart data={MOCK_EXPOSURE} />
                </div>
              </div>
            </>
          )}
        </div>

        {/* Config panel */}
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="flex items-center gap-2 mb-4">
            <Settings className="w-4 h-4 text-muted-foreground" aria-hidden />
            <h2 className="text-sm font-semibold text-foreground">Risk Parameters</h2>
          </div>

          {riskConfig ? (
            <div className="space-y-0">
              <ConfigInput
                label="Risk/Trade"
                value={cfg.risk_per_trade_pct ?? riskConfig.risk_per_trade_pct}
                onChange={(v) => setLocalConfig((p) => ({ ...p, risk_per_trade_pct: v }))}
              />
              <ConfigInput
                label="Max Position"
                value={cfg.max_position_size_pct ?? riskConfig.max_position_size_pct}
                onChange={(v) => setLocalConfig((p) => ({ ...p, max_position_size_pct: v }))}
              />
              <ConfigInput
                label="Max Exposure"
                value={cfg.max_total_exposure_pct ?? riskConfig.max_total_exposure_pct}
                onChange={(v) => setLocalConfig((p) => ({ ...p, max_total_exposure_pct: v }))}
              />
              <ConfigInput
                label="Daily DD Limit"
                value={cfg.daily_drawdown_limit_pct ?? riskConfig.daily_drawdown_limit_pct}
                onChange={(v) => setLocalConfig((p) => ({ ...p, daily_drawdown_limit_pct: v }))}
              />
              <ConfigInput
                label="Max Drawdown"
                value={cfg.max_drawdown_limit_pct ?? riskConfig.max_drawdown_limit_pct}
                onChange={(v) => setLocalConfig((p) => ({ ...p, max_drawdown_limit_pct: v }))}
              />
              <ConfigInput
                label="Max Positions"
                value={cfg.max_positions ?? riskConfig.max_positions}
                unit="n"
                onChange={(v) => setLocalConfig((p) => ({ ...p, max_positions: v }))}
              />
              <ConfigInput
                label="Consec. Losses Limit"
                value={cfg.max_consecutive_losses ?? riskConfig.max_consecutive_losses}
                unit="n"
                onChange={(v) => setLocalConfig((p) => ({ ...p, max_consecutive_losses: v }))}
              />
              <ConfigInput
                label="Cooldown"
                value={cfg.cooldown_minutes ?? riskConfig.cooldown_minutes}
                unit="min"
                onChange={(v) => setLocalConfig((p) => ({ ...p, cooldown_minutes: v }))}
              />

              {Object.keys(localConfig).length > 0 && (
                <div className="pt-3">
                  <button
                    onClick={handleConfigSave}
                    disabled={isSaving}
                    className="w-full py-2 rounded-md bg-primary text-primary-foreground text-xs font-semibold hover:bg-primary/90 disabled:opacity-60 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {isSaving ? 'Saving...' : 'Save Changes'}
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-2 animate-pulse">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="h-8 bg-muted rounded" />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Alert history */}
      <div className="bg-card border border-border rounded-lg p-4">
        <h2 className="text-sm font-semibold text-foreground mb-3">
          Risk Alerts
          {alerts.filter((a) => !a.acknowledged).length > 0 && (
            <span className="ml-2 text-[10px] bg-loss/10 text-loss px-1.5 py-0.5 rounded">
              {alerts.filter((a) => !a.acknowledged).length} unacknowledged
            </span>
          )}
        </h2>

        {alerts.length === 0 ? (
          <div className="flex items-center gap-2 text-sm text-profit py-2">
            <CheckCircle className="w-4 h-4" aria-hidden />
            No active alerts — all systems normal
          </div>
        ) : (
          <div className="space-y-2">
            {alerts.map((alert) => (
              <div
                key={alert.id}
                className={cn(
                  'flex items-start gap-3 p-3 rounded-lg border',
                  alert.level === 'critical' || alert.level === 'emergency'
                    ? 'bg-loss/5 border-loss/20'
                    : alert.level === 'warning'
                      ? 'bg-yellow-500/5 border-yellow-500/20'
                      : 'bg-blue-500/5 border-blue-500/20'
                )}
                role="alert"
              >
                <AlertTriangle
                  className={cn('w-4 h-4 flex-shrink-0 mt-0.5', getAlertColor(alert.level))}
                  aria-hidden
                />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-foreground">{alert.message}</p>
                  {alert.current_value !== undefined && (
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Current: {alert.current_value.toFixed(2)} / Threshold: {alert.threshold_value?.toFixed(2)}
                    </p>
                  )}
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    {formatDateTime(alert.created_at)}
                  </p>
                </div>
                <span className={cn('text-[10px] font-semibold uppercase', getAlertColor(alert.level))}>
                  {alert.level}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
