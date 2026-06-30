'use client';
import { DollarSign, TrendingUp, Activity, BarChart2 } from 'lucide-react';
import { StatCard } from '@/components/common/StatCard';
import { TradingChart } from '@/components/charts/TradingChart';
import { PositionsList } from '@/components/trading/PositionsList';
import { SessionClock } from '@/components/session/SessionClock';
import { AISignalCard } from '@/components/ai/AISignalCard';
import { ConsensusGauge } from '@/components/ai/ConsensusGauge';
import { RiskDashboard } from '@/components/risk/RiskDashboard';
import { useTradingStore } from '@/lib/store/tradingStore';
import { useAISignals } from '@/lib/hooks/useAISignals';
import { useRiskState } from '@/lib/hooks/useRiskState';
import { usePositions } from '@/lib/hooks/usePositions';
import { formatCurrency, formatPnL, formatPercent } from '@/lib/utils/formatters';
import { getPnLColor } from '@/lib/utils/colors';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';

export function DashboardClient() {
  const account = useTradingStore((s) => s.account);
  const { signal, isLoading: signalLoading } = useAISignals();
  const { riskState } = useRiskState();
  const { positions } = usePositions();

  const balance = account?.balance ?? 125_430.5;
  const equity = account?.equity ?? 126_842.3;
  const dayPnl = account?.day_pnl ?? 2340.5;
  const dayPnlPct = account?.day_pnl_pct ?? 1.87;

  const totalUnrealizedPnl = positions.reduce((s, p) => s + p.unrealized_pnl, 0);
  const winningPositions = positions.filter((p) => p.unrealized_pnl > 0).length;
  const winRate =
    positions.length > 0 ? (winningPositions / positions.length) * 100 : 0;

  const agentsAgreeing = signal?.agents.filter((a) => a.signal === signal.direction).length ?? 0;

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Row 1: Stat Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          label="Account Balance"
          value={formatCurrency(balance)}
          icon={DollarSign}
          trend={dayPnlPct}
          trendLabel={`${dayPnlPct > 0 ? '+' : ''}${dayPnlPct.toFixed(2)}% today`}
          iconColor="text-primary"
        />
        <StatCard
          label="Day P&L"
          value={formatPnL(dayPnl)}
          icon={TrendingUp}
          trend={dayPnlPct}
          valueClassName={getPnLColor(dayPnl)}
          iconColor={dayPnl >= 0 ? 'text-profit' : 'text-loss'}
        />
        <StatCard
          label="Open Positions"
          value={positions.length.toString()}
          icon={Activity}
          subValue={positions.length > 0 ? `${formatPnL(totalUnrealizedPnl)} unrealized` : undefined}
          valueClassName={totalUnrealizedPnl >= 0 ? 'text-foreground' : 'text-loss'}
          iconColor="text-blue-400"
        />
        <StatCard
          label="Floating P&L"
          value={formatPnL(totalUnrealizedPnl)}
          icon={BarChart2}
          trend={positions.length > 0 ? (totalUnrealizedPnl / balance) * 100 : 0}
          valueClassName={getPnLColor(totalUnrealizedPnl)}
          iconColor={totalUnrealizedPnl >= 0 ? 'text-profit' : 'text-loss'}
        />
      </div>

      {/* Row 2: Chart + Right Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-3" style={{ minHeight: '420px' }}>
        {/* Chart: 60% */}
        <div className="lg:col-span-3 h-[420px]">
          <ErrorBoundary>
            <TradingChart />
          </ErrorBoundary>
        </div>

        {/* Right panel: 40% */}
        <div className="lg:col-span-2 flex flex-col gap-3">
          {/* Session Clock */}
          <div className="bg-card border border-border rounded-lg p-3">
            <ErrorBoundary>
              <SessionClock />
            </ErrorBoundary>
          </div>

          {/* AI Signal + Consensus */}
          <div className="flex-1 overflow-hidden">
            <div className="bg-card border border-border rounded-lg p-3 h-full overflow-y-auto scrollbar-hidden">
              <div className="flex items-start gap-4">
                <div className="flex-1 min-w-0">
                  <ErrorBoundary>
                    <AISignalCard signal={signal} isLoading={signalLoading} />
                  </ErrorBoundary>
                </div>
                {signal && (
                  <div className="flex-shrink-0">
                    <ConsensusGauge
                      confidence={signal.confidence}
                      direction={signal.direction}
                      agentCount={signal.agents.length}
                      agentsAgreeing={agentsAgreeing}
                    />
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Row 3: Positions + Risk */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {/* Positions */}
        <div className="bg-card border border-border rounded-lg p-3">
          <ErrorBoundary>
            <PositionsList maxHeight="360px" />
          </ErrorBoundary>
        </div>

        {/* Risk Dashboard */}
        <div className="bg-card border border-border rounded-lg p-3">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-sm font-semibold text-foreground">Risk Monitor</span>
            {riskState?.is_circuit_breaker_active && (
              <span className="text-[10px] bg-loss/10 text-loss px-1.5 py-0.5 rounded font-medium">
                CIRCUIT BREAKER
              </span>
            )}
          </div>
          <ErrorBoundary>
            <RiskDashboard />
          </ErrorBoundary>
        </div>
      </div>
    </div>
  );
}
