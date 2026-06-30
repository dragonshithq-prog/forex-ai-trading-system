'use client';
import { DollarSign, TrendingUp, Activity, BarChart2, Shield, Zap, Clock } from 'lucide-react';
import { StatCard } from '@/components/common/StatCard';
import { TradingChart } from '@/components/charts/TradingChart';
import { PositionsList } from '@/components/trading/PositionsList';
import { SessionClock } from '@/components/session/SessionClock';
import { AISignalCard } from '@/components/ai/AISignalCard';
import { ConsensusGauge } from '@/components/ai/ConsensusGauge';
import { RiskDashboard } from '@/components/risk/RiskDashboard';
import { Watchlist } from '@/components/market/Watchlist';
import { MarketHeatmap } from '@/components/market/MarketHeatmap';
import { ActivityFeed } from '@/components/common/ActivityFeed';
import { useTradingStore } from '@/lib/store/tradingStore';
import { useAISignals } from '@/lib/hooks/useAISignals';
import { useRiskState } from '@/lib/hooks/useRiskState';
import { usePositions } from '@/lib/hooks/usePositions';
import { useMarketStore } from '@/lib/store/marketStore';
import { formatCurrency, formatPnL, formatPercent } from '@/lib/utils/formatters';
import { getPnLColor } from '@/lib/utils/colors';
import { cn } from '@/lib/utils/cn';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { useEffect, useCallback } from 'react';

export function DashboardClient() {
  const account = useTradingStore((s) => s.account);
  const { signal, isLoading: signalLoading } = useAISignals();
  const { riskState } = useRiskState();
  const { positions } = usePositions();
  const setSelectedSymbol = useMarketStore((s) => s.setSelectedSymbol);
  const selectedSymbol = useMarketStore((s) => s.selectedSymbol);

  const balance = account?.balance ?? 125_430.5;
  const equity = account?.equity ?? 126_842.3;
  const dayPnl = account?.day_pnl ?? 2340.5;
  const dayPnlPct = account?.day_pnl_pct ?? 1.87;
  const marginUsed = account?.margin_used ?? 8420;
  const freeMargin = account?.margin_available ?? 118_422;
  const marginLevel = account?.margin_used ? (equity / account.margin_used) * 100 : 999;

  const totalUnrealizedPnl = positions.reduce((s, p) => s + p.unrealized_pnl, 0);
  const winningPositions = positions.filter((p) => p.unrealized_pnl > 0).length;
  const winRate = positions.length > 0 ? (winningPositions / positions.length) * 100 : 0;

  const agentsAgreeing = signal?.agents.filter((a) => a.signal === signal.direction).length ?? 0;

  const handleSymbolSelect = useCallback((symbol: string) => {
    setSelectedSymbol(symbol);
  }, [setSelectedSymbol]);

  useEffect(() => {
    const handler = (e: Event) => {
      const custom = e as CustomEvent<string>;
      if (custom.detail) setSelectedSymbol(custom.detail);
    };
    window.addEventListener('symbol-select', handler as EventListener);
    return () => window.removeEventListener('symbol-select', handler as EventListener);
  }, [setSelectedSymbol]);

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Row 1: Stat Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
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

      {/* Row 2: Quick Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-card border border-border rounded-lg p-3">
          <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium mb-1">Margin Used</div>
          <div className="font-mono text-sm font-semibold text-foreground tabular-nums">{formatCurrency(marginUsed)}</div>
          <div className="text-[10px] text-muted-foreground mt-0.5">{((marginUsed / equity) * 100).toFixed(1)}% of equity</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-3">
          <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium mb-1">Free Margin</div>
          <div className="font-mono text-sm font-semibold text-foreground tabular-nums">{formatCurrency(freeMargin)}</div>
          <div className="text-[10px] text-muted-foreground mt-0.5">Available for trading</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-3">
          <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium mb-1">Margin Level</div>
          <div className={cn('font-mono text-sm font-semibold tabular-nums', marginLevel > 200 ? 'text-profit' : marginLevel > 100 ? 'text-yellow-400' : 'text-loss')}>
            {marginLevel > 999 ? '∞' : `${marginLevel.toFixed(0)}%`}
          </div>
          <div className="text-[10px] text-muted-foreground mt-0.5">Equity / Margin</div>
        </div>
        <div className="bg-card border border-border rounded-lg p-3">
          <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium mb-1">Win Rate</div>
          <div className="font-mono text-sm font-semibold text-foreground tabular-nums">{winRate.toFixed(1)}%</div>
          <div className="text-[10px] text-muted-foreground mt-0.5">{winningPositions}/{positions.length} winners</div>
        </div>
      </div>

      {/* Row 3: Chart + Right Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4" style={{ minHeight: '420px' }}>
        {/* Chart: 60% */}
        <div className="lg:col-span-3 h-[420px]">
          <ErrorBoundary>
            <TradingChart />
          </ErrorBoundary>
        </div>

        {/* Right panel: 40% */}
        <div className="lg:col-span-2 flex flex-col gap-3">
          {/* Session Clock */}
          <div className="bg-card border border-border rounded-xl p-4">
            <ErrorBoundary>
              <SessionClock />
            </ErrorBoundary>
          </div>

          {/* AI Signal */}
          <div className="flex-1 overflow-hidden">
            <ErrorBoundary>
              <AISignalCard signal={signal} isLoading={signalLoading} />
            </ErrorBoundary>
          </div>

          {/* Consensus Gauge */}
          {signal && (
            <div className="bg-card border border-border rounded-lg p-4">
              <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-semibold mb-3 text-center">
                Multi-Agent Consensus
              </div>
              <div className="flex items-center justify-center">
                <ConsensusGauge
                  confidence={signal.confidence}
                  direction={signal.direction}
                  agentCount={signal.agents.length}
                  agentsAgreeing={agentsAgreeing}
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Row 4: Positions + Risk */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Positions */}
        <div className="bg-card border border-border rounded-xl p-4">
          <ErrorBoundary>
            <PositionsList maxHeight="360px" />
          </ErrorBoundary>
        </div>

        {/* Risk Dashboard */}
        <div className="bg-card border border-border rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Shield className="w-4 h-4 text-muted-foreground" aria-hidden />
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

      {/* Row 5: Watchlist + Heatmap + Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Watchlist */}
        <div className="bg-card border border-border rounded-xl p-4">
          <Watchlist onSymbolSelect={handleSymbolSelect} />
        </div>

        {/* Market Heatmap */}
        <div className="bg-card border border-border rounded-xl p-4">
          <MarketHeatmap />
        </div>

        {/* Activity Feed */}
        <div className="bg-card border border-border rounded-xl p-4">
          <ActivityFeed />
        </div>
      </div>
    </div>
  );
}
